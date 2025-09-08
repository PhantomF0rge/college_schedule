from django.db import models
from django.utils import timezone
from directory.models import Room, LessonType, Discipline, Teacher, StudentGroup
from django.core.exceptions import ValidationError

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
        # уже есть unique_together по (date, timeslot, group)
        if not self.is_remote and not self.room:
            raise ValidationError("Для очной пары нужно указать кабинет.")

        # Занятость аудитории
        if self.room and not self.is_remote:
            clash_room = Lesson.objects.filter(
                date=self.date, timeslot=self.timeslot, room=self.room
            ).exclude(pk=self.pk).exists()
            if clash_room:
                raise ValidationError(f"Кабинет {self.room} уже занят в этот слот.")

            # вместимость и компьютеры
            if self.group and self.group.size:
                if self.room.capacity and self.group.size > self.room.capacity:
                    raise ValidationError(
                        f"Группа ({self.group.size}) не помещается в кабинет (вместимость {self.room.capacity})."
                    )
                if self.room.computers and self.group.size > self.room.computers:
                    raise ValidationError(
                        f"Недостаточно компьютеров: нужно {self.group.size}, есть {self.room.computers}."
                    )

        # Занятость преподавателя
        if self.teacher:
            clash_teacher = Lesson.objects.filter(
                date=self.date, timeslot=self.timeslot, teacher=self.teacher
            ).exclude(pk=self.pk).exists()
            if clash_teacher:
                raise ValidationError(f"Преподаватель {self.teacher} уже занят в этот слот.")

        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()  # чтобы проверки сработали из админки/скриптов
        return super().save(*args, **kwargs)

class HomeworkItem(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="homework")
    text = models.TextField()

    def __str__(self):
        return f"ДЗ: {self.lesson}"
