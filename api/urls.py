from django.urls import path
from . import views

urlpatterns = [
    path("suggest/groups/", views.suggest_groups),
    path("suggest/teachers/", views.suggest_teachers),
    path("suggest/disciplines/", views.suggest_disciplines),
    path("schedule/today/", views.schedule_today),
    path("schedule/period/", views.schedule_period),
    path("prefs/set_group/", views.set_preferred_group),
    path("prefs/get_group/", views.get_preferred_group),
    path("search/suggest/", views.suggest_any),
    path("teacher/homework/set/", views.teacher_set_homework),
    path("teacher/room/free/", views.teacher_free_rooms),
    path("teacher/room/change/", views.teacher_change_room),
    path("teacher/me/schedule/", views.teacher_me_schedule),
    path("teacher/me/stats/", views.teacher_me_stats),
    path("admin/generate/", views.admin_generate_schedule),
    path("admin/groups/", views.admin_list_groups),
    path("admin/teachers/", views.admin_list_teachers),
    path("admin/teacher/schedule/", views.admin_teacher_schedule),
    path("admin/schedule/period_all/", views.admin_schedule_period_all),

    # Studio CRUD
    path("studio/teachers/", views.studio_teachers),
    path("studio/teachers/<int:pk>/", views.studio_teachers_item),

    path("studio/buildings/", views.studio_buildings),
    path("studio/buildings/<int:pk>/", views.studio_buildings_item),

    path("studio/rooms/", views.studio_rooms),
    path("studio/rooms/<int:pk>/", views.studio_rooms_item),

    path("studio/groups/", views.studio_groups),
    path("studio/groups/<int:pk>/", views.studio_groups_item),

    path("studio/disciplines/", views.studio_disciplines),
    path("studio/disciplines/<int:pk>/", views.studio_disciplines_item),

    path("studio/lessontypes/", views.studio_lessontypes),
    path("studio/lessontypes/<int:pk>/", views.studio_lessontypes_item),

    path("studio/assignments/", views.studio_assignments),
    path("studio/assignments/<int:pk>/", views.studio_assignments_item),

    path("studio/plans/", views.studio_plans),
    path("studio/plans/<int:pk>/", views.studio_plans_item),

    path("studio/lessons/", views.studio_lessons),
    path("studio/lessons/<int:pk>/", views.studio_lessons_item),

    path("studio/options/", views.studio_options),

    #exports
    path("export/ics/", views.export_ics),
    path("export/csv/", views.export_csv),

    #интеграция под актуалочку с зфранепарасп
    path("integrations/ranepa/fetch/", views.ranepa_fetch, name="ranepa_fetch"),

    path("integrations/ranepa/fetch/",  views.ranepa_fetch,  name="ranepa_fetch"),
    path("integrations/ranepa/import/", views.ranepa_import, name="ranepa_import"),
]
