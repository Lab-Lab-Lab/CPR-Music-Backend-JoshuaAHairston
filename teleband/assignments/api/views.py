from collections import defaultdict
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from django.db.models import OuterRef, Subquery

from .serializers import (
    AssignmentViewSetSerializer,
    AssignmentInstrumentSerializer,
    AssignmentSerializer,
)
from teleband.assignments.api.serializers import ActivitySerializer, PiecePlanSerializer
from teleband.musics.api.serializers import PartTranspositionSerializer

from teleband.assignments.models import Assignment, Activity, AssignmentGroup, PiecePlan
from teleband.courses.models import Course
from teleband.utils.permissions import IsTeacher


class TeacherUpdate(IsTeacher):
    def has_permission(self, request, view):
        if view.action not in ["update", "partial_update"]:
            return True

        return super().has_permission(request, view)


class ActivityViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    serializer_class = ActivitySerializer
    queryset = Activity.objects.all()
    lookup_field = "id"
    permission_classes = [IsTeacher]

    def get_queryset(self):
        # Define a subquery to get the first assignment for each activity
        distinct_activity_assignments = (
            Assignment.objects.filter(
                enrollment__course__slug=self.kwargs["course_slug_slug"],
                activity=OuterRef("id"),
            )
            .order_by("id", "pk")
            .values("activity_id")[:1]
        )

        # Use the subquery to filter the main queryset
        queryset = self.queryset.filter(pk__in=Subquery(distinct_activity_assignments))

        return queryset


class AssignmentViewSet(
    RetrieveModelMixin, UpdateModelMixin, ListModelMixin, GenericViewSet
):
    serializer_class = AssignmentViewSetSerializer
    queryset = Assignment.objects.all()
    lookup_field = "id"
    permission_classes = [TeacherUpdate]

    def get_serializer_class(self):
        if self.action in ["update", "partial_update"]:
            return AssignmentInstrumentSerializer
        elif self.action == "retrieve":
            return AssignmentSerializer
        return self.serializer_class

    @action(detail=True)
    def notation(self, request, *args, **kwargs):
        course = Course.objects.get(slug=self.kwargs["course_slug_slug"])
        assignment = self.get_object()

        part_transposition = assignment.part.transpositions.get(
            transposition=assignment.instrument.transposition
        )

        serializer = PartTranspositionSerializer(
            part_transposition, context=self.get_serializer_context()
        )
        return Response(serializer.data)

    def get_queryset(self):
        course = Course.objects.get(slug=self.kwargs["course_slug_slug"])
        role = self.request.user.enrollment_set.get(course=course).role

        if role.name == "Student":
            return (
                Assignment.objects.filter(
                    enrollment__course=course, enrollment__user=self.request.user
                )
                .select_related(
                    "activity",
                    "instrument",
                    "piece",
                    "activity__part_type",
                    "instrument__transposition",
                    "group",
                )
                .prefetch_related("submissions")
            )
        if role.name == "Teacher":
            return Assignment.objects.filter(enrollment__course=course).select_related(
                "activity",
                "instrument",
                "piece",
                "activity__part_type",
                "instrument__transposition",
                "group",
            )

    def list(self, request, *args, **kwargs):
        assignments = self.get_queryset()

        serialized = AssignmentViewSetSerializer(
            assignments, context={"request": request}, many=True
        )

        grouped = defaultdict(list)
        for assignment in serialized.data:
            key = assignment["piece_slug"]
            grouped[key].append(assignment)

        ordering = {
            "Melody": 1,
            "Bassline": 2,
            "Creativity": 3,
            "Reflection": 4,
            "Connect": 5,
            "Aural": 3,
            "Exploratory": 3,
            "Theoretical": 3,
            "MelodyPost": 3.1,
            "BasslinePost": 3.2,
        }

        # FIXME: this should respect order from server/pieceplan and mayeb do this as a backup?
        orderFromActivityType = lambda a: ordering[a["activity_type_name"].split()[0]]
        for pieceplan in grouped:
            grouped[pieceplan].sort(key=orderFromActivityType)

        return Response(grouped)


class PiecePlanViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    serializer_class = PiecePlanSerializer
    queryset = PiecePlan.objects.prefetch_related("piece")
    lookup_field = "id"
    permission_classes = [IsTeacher]

    def get_queryset(self):
        course = Course.objects.get(slug=self.kwargs["course_slug_slug"])
        return PiecePlan.objects.filter(curriculum__course=course).prefetch_related(
            "piece"
        )

    # def get_serializer_class(self):
    #     if self.action == "create":
    #         return PieceCreateSerializer
    #     return self.serializer_class
