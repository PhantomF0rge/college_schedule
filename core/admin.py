from django.contrib import admin
from .models import SiteConfig

@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("maintenance_enabled", "maintenance_hard", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("maintenance_enabled", "maintenance_hard", "message")
        }),
        ("Служебное", {
            "fields": ("updated_at",),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("updated_at",)

    # одна запись: разрешаем Add только если записей ещё нет
    def has_add_permission(self, request):
        return SiteConfig.objects.count() == 0
