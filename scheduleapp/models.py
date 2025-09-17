from django.db import models
from django.utils import timezone
from directory.models import Room, LessonType, Discipline, Teacher, StudentGroup
from django.core.exceptions import ValidationError
from django.conf import settings

class TimeSlot(models.Model):
    # порядковый номер пары в дне: 1,2,3...
    order = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["order"]
        unique_together = ("order", "start_time", "end_time")

    def __str__(self):
        return f"{self.order} пара: {self.start_time}–{self.end_time}"

class Lesson(models.Model):
    date = models.DateField()
    timeslot = models.ForeignKey(TimeSlot, on_delete=models.PROTECT)
    group = models.ForeignKey(StudentGroup, on_delete=models.PROTECT, related_name="lessons")
    discipline = models.ForeignKey(Discipline, on_delete=models.PROTECT)
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name="lessons")
    lesson_type = models.ForeignKey(LessonType, on_delete=models.PROTECT)
    room = models.ForeignKey(Room, on_delete=models.PROTECT, null=True, blank=True)  # может быть дистанционка
    is_remote = models.BooleanField(default=False)  # СДО / дистанционно
    remote_platform = models.CharField(max_length=120, blank=True)  # СДО ссылка/название
    is_stream = models.BooleanField(
        default=False,
        help_text="Потоковая лекция (одно занятие для нескольких групп одновременно)"
    )

    class Meta:
        ordering = ["date", "timeslot__order"]
        unique_together = ("date", "timeslot", "group")  # одна группа — одна пара в этот слот

    def status_for_now(self):
        now = timezone.localtime()
        if self.date != now.date():
            return "past" if self.date < now.date() else "upcoming"
        start = timezone.make_aware(timezone.datetime.combine(self.date, self.timeslot.start_time))
        end = timezone.make_aware(timezone.datetime.combine(self.date, self.timeslot.end_time))
        if start <= now <= end:
            return "ongoing"
        return "past" if now > end else "upcoming"

    def clean(self):
        super().clean()
        # Ищем все занятия в тот же день и слот
        qs = Lesson.objects.filter(date=self.date, timeslot=self.timeslot).exclude(pk=self.pk)

        # ---- Teacher conflicts ----
        if self.teacher_id:
            clashes = qs.filter(teacher_id=self.teacher_id)

            # Разрешаем «одновременность», если это один и тот же поток:
            #  - текущий и все конфликты помечены is_stream=True
            #  - совпадают дисциплина/тип/формат (очно/СДО) и платформа
            if self.is_stream:
                bad = clashes.exclude(
                    is_stream=True,
                    discipline_id=self.discipline_id,
                    lesson_type_id=self.lesson_type_id,
                    is_remote=self.is_remote,
                    remote_platform=self.remote_platform,
                )
                if bad.exists():
                    raise ValidationError({"teacher": "Конфликт у преподавателя вне потока"})
            else:
                if clashes.exists():
                    raise ValidationError({"teacher": "Преподаватель уже занят в этот слот"})

        # ---- Room conflicts ----
        # Для потоков разрешаем делить одну аудиторию несколькими группами,
        # если это один и тот же «поток» (см. критерии выше)
        if self.room_id:
            r_clashes = qs.filter(room_id=self.room_id)
            if self.is_stream:
                bad = r_clashes.exclude(
                    is_stream=True,
                    discipline_id=self.discipline_id,
                    lesson_type_id=self.lesson_type_id,
                    is_remote=self.is_remote,
                    remote_platform=self.remote_platform,
                )
                if bad.exists():
                    raise ValidationError({"room": "Конфликт аудитории вне потока"})
            else:
                if r_clashes.exists():
                    raise ValidationError({"room": "Аудитория занята"})

    def save(self, *args, **kwargs):
        self.full_clean()  # чтобы проверки сработали из админки/скриптов
        return super().save(*args, **kwargs)

class HomeworkItem(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="homework")
    text = models.TextField()

    def __str__(self):
        return f"ДЗ: {self.lesson}"

class ImportJob(models.Model):
    SOURCE_CHOICES = [
        ("RANEPA", "RANEPA"),
        ("OTHER", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Пользователь"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default="RANEPA", verbose_name="Источник")

    # что запрашивали / мета
    params = models.JSONField(default=dict, blank=True, verbose_name="Параметры запроса")
    # сводные итоги: created/updated/skipped/errors + reasons
    totals = models.JSONField(default=dict, blank=True, verbose_name="Итоги")
    reasons = models.JSONField(default=dict, blank=True, verbose_name="Причины")
    samples = models.JSONField(default=list, blank=True, verbose_name="Примеры проблемных записей")

    # относительный путь к файлу лога в MEDIA_ROOT (например: import_logs/ranepa_YYYY.json)
    log_file = models.CharField(max_length=255, blank=True, verbose_name="Файл лога")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Импорт"
        verbose_name_plural = "Импорты"

    def __str__(self):
        return f"[{self.source}] {self.created_at:%Y-%m-%d %H:%M}"