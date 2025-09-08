# directory/admin.py
from django.contrib import admin
from .models import (
    Building, RoomType, Room, LessonType, Discipline, Teacher, StudentGroup,
    TeacherWorkload, TeacherDayOverride, GroupDisciplinePlan,
    TeachingAssignment, Holiday, BuildingPriority
)

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user")
    search_fields = ("full_name",)
    autocomplete_fields = ("user",)

@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ("title", "delivery_mode", "default_lesson_type", "required_room_type", "requires_computers")
    list_filter = ("delivery_mode", "required_room_type", "requires_computers")
    search_fields = ("title",)

admin.site.register(Building)
admin.site.register(RoomType)
admin.site.register(Room)
admin.site.register(LessonType)
admin.site.register(StudentGroup)
admin.site.register(TeacherWorkload)
admin.site.register(TeacherDayOverride)
admin.site.register(GroupDisciplinePlan)
admin.site.register(TeachingAssignment)
admin.site.register(Holiday)
admin.site.register(BuildingPriority)
