from django.contrib import admin
from .models import TimeSlot, Lesson, HomeworkItem

admin.site.register(TimeSlot)
admin.site.register(Lesson)
admin.site.register(HomeworkItem)
