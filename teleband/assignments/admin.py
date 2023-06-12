from django.contrib import admin
from reversion.admin import VersionAdmin

from .models import ActivityCategory, ActivityType, Activity, Assignment, PiecePlan, PlannedActivity


@admin.register(ActivityCategory)
class ActivityCategoryAdmin(VersionAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(ActivityType)
class ActivityTypeAdmin(VersionAdmin):
    list_display = ("id", "name", "category")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(Activity)
class ActivityAdmin(VersionAdmin):
    list_display = ("id", "activity_type", "part_type", "body")
    list_filter = ("activity_type", "part_type")


@admin.register(Assignment)
class AssignmentAdmin(VersionAdmin):
    list_display = (
        "id",
        "activity",
        "enrollment",
        "part",
        "deadline",
        "instrument",
        "created_at",
    )
    list_filter = (
        "activity",
        "enrollment",
        "part",
        "deadline",
        "instrument",
        "created_at",
    )
    date_hierarchy = "created_at"

class PiecePlanActivityInline(admin.TabularInline):
    model = PlannedActivity
    extra = 0
    ordering = ("order",)

@admin.register(PiecePlan)
class PiecePlanAdmin(VersionAdmin):
    list_display = (
        "id", 
        "name",
        "piece", 
    )
    list_filter = (
        ("piece", admin.RelatedOnlyFieldListFilter),
    )
    inlines = (PiecePlanActivityInline,)
    raw_id_fields = ("activities",)

@admin.register(PlannedActivity)
class PlannedActivityAdmin(VersionAdmin):
    list_display = (
        "id", 
        "piece_plan", 
        "activity",
    )
    list_filter = (
        "piece_plan",
        "activity",
    )