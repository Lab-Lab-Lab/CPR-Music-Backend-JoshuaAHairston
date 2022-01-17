import collections
import csv
from io import StringIO
import logging

from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import (
    ListModelMixin,
    RetrieveModelMixin,
    CreateModelMixin,
    DestroyModelMixin,
    UpdateModelMixin,
)
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .serializers import (
    EnrollmentSerializer,
    CourseSerializer,
    CourseRelatedSerializer,
    EnrollmentInstrumentSerializer,
    RosterSerializer,
)
from teleband.assignments.api.serializers import AssignmentSerializer
from teleband.users.api.serializers import UserSerializer

from teleband.courses.models import Enrollment, Course
from teleband.assignments.models import Assignment, Activity
from teleband.musics.models import Piece, Part
from teleband.users.models import Role
from teleband.utils.permissions import IsTeacher

logger = logging.getLogger(__name__)


User = get_user_model()

class IsTeacherEnrollment(permissions.BasePermission):
    def has_permission(self, request, view):
        if view.action not in ["update", "partial_update", "destroy"]:
            return True
        try:
            print("The get object {}".format(view.get_object()))
            e = Enrollment.objects.get(
                user=request.user, course=view.get_object().course
            )
            return e.role.name == "Teacher"
        except Enrollment.DoesNotExist:
            logger.info(
                "No Enrollment for {} in {}".format(request.user, view.get_object())
            )
        return False


class EnrollmentViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    GenericViewSet,
):
    serializer_class = EnrollmentSerializer
    queryset = Enrollment.objects.all()
    permission_classes = [IsTeacherEnrollment]

    def get_queryset(self, *args, **kwargs):
        if self.action in ["update", "partial_update", "destroy"]:
            courses = [
                e.course
                for e in Enrollment.objects.filter(
                    user=self.request.user, role__name="Teacher"
                )
            ]
            return self.queryset.filter(course__in=courses)

        return self.queryset.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "update" or self.action == "partial_update":
            return EnrollmentInstrumentSerializer
        return self.serializer_class


class CoursePermission(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        if view.action == "create":
            return request.user.groups.filter(name="Teacher").exists()
        return True

    def has_object_permission(self, request, view, obj):
        if view.action == "retrieve":
            return super().has_permission(request, view)
        try:
            e = Enrollment.objects.get(user=request.user, course=obj)
            return e.role.name == "Teacher"
        except Enrollment.DoesNotExist:
            logger.info("No Enrollment for {} in {}".format(request.user, obj))
        return False


class CourseViewSet(RetrieveModelMixin, CreateModelMixin, GenericViewSet):
    serializer_class = CourseSerializer
    queryset = Course.objects.all()
    lookup_field = "slug"
    permission_classes = [CoursePermission]

    def get_serializer_class(self):
        if self.action == "create":
            return CourseRelatedSerializer
        return self.serializer_class

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["get", "post"])
    def roster(self, request, **kwargs):
        if request.method == "POST":
            # bulk student/enrollment creation
            users_file = request.FILES["file"]
            contents = "".join([line.decode("utf-8") for line in users_file.readlines()])
            reader = csv.reader(StringIO(contents))

            response = collections.defaultdict(list)

            for name, username, password, grade in reader:
                try: 
                    user = User.objects.get(username=username)
                    if user.check_password(password):
                        response["existing"].append(user)
                    else:
                        response["invalid"].append({
                            "name": name,
                            "username": username,
                            "password": password,
                            "grade": grade,
                            "reason": "Wrong password"  # real bad 
                        })
                except User.DoesNotExist:
                    response["created"].append(
                        User.objects.create_user(
                            name=name, username=username, password=password, grade=grade
                        )
                    )

            course = self.get_object()
            role = Role.objects.get(name="Student")
            enrollments = collections.defaultdict(list)

            for key in ["created", "existing"]:
                for user in response[key]:
                    try:
                        enrollments["existing"].append(Enrollment.objects.get(user=user, course=course))
                    except Enrollment.DoesNotExist:
                        enrollments["created"].append(Enrollment.objects.create(
                            user=user,
                            course=course,
                            # instrument=user.instrument,
                            role=role
                        ))

            response["created"] = UserSerializer(
                response["created"], many=True, context={"request": request}
            ).data
            response["existing"] = UserSerializer(
                response["existing"], many=True, context={"request": request}
            ).data
            enrollments["created"] = EnrollmentSerializer(
                enrollments["created"], many=True, context={"request": request}
            ).data
            enrollments["existing"] = EnrollmentSerializer(
                enrollments["existing"], many=True, context={"request": request}
            ).data
            return Response(status=status.HTTP_200_OK, data={"users": response, "enrollments": enrollments})


        # must be a GET, respond with all enrollments for this class
        course_enrollments = Enrollment.objects.filter(course=self.get_object())
        serializer = RosterSerializer(
            course_enrollments, many=True, context={"request": request}
        )
        return Response(status=status.HTTP_200_OK, data=serializer.data)
        

    @action(detail=True, methods=["post"])
    def assign(self, request, **kwargs):
        if "piece_id" not in request.POST:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Missing piece_id in POST data"},
            )

        try:
            piece = Piece.objects.get(pk=request.POST["piece_id"])
        except Piece.DoesNotExist:
            logger.info(
                "Attempt to assign non-existent piece {}".format(
                    request.POST["piece_id"]
                )
            )
            return Response(status=status.HTTP_404_NOT_FOUND)

        course = self.get_object()

        assignments = []
        for activity in Activity.objects.all():
            # Get this piece’s part for this kind of activity
            part = Part.objects.get(piece=piece, part_type=activity.part_type)
            for e in Enrollment.objects.filter(course=course, role__name="Student"):
                assignments.append(
                    Assignment.objects.create(
                        activity=activity,
                        enrollment=e,
                        instrument=e.instrument,
                        part=part,
                    )
                )

        serializer = AssignmentSerializer(
            assignments, many=True, context={"request": request}
        )
        return Response(status=status.HTTP_200_OK, data=serializer.data)
