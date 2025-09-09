from django.contrib import admin
from .models import TimeSlot, Lesson, HomeworkItem, ImportJob

admin.site.register(TimeSlot)
admin.site.register(Lesson)
admin.site.register(HomeworkItem)

@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ("created_at","source","user","_created","_updated","_skipped","_errors")
    readonly_fields = ("created_at","source","user","params","totals","reasons","samples","log_file")
    def _created(self,obj): return (obj.totals or {}).get("created",0)
    def _updated(self,obj): return (obj.totals or {}).get("updated",0)
    def _skipped(self,obj): return (obj.totals or {}).get("skipped",0)
    def _errors(self,obj):  return (obj.totals or {}).get("errors",0)