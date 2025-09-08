from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

class Building(models.Model):
    name = models.CharField(max_length=120)

    def __str__(self):
        return self.name

class RoomType(models.Model):
    name = models.CharField(max_length=120)  # спортзал, компьютерный и т.д.

    def __str__(self):
        return self.name

class Room(models.Model):
    building = models.ForeignKey(Building, on_delete=models.PROTECT, related_name="rooms")
    name = models.CharField(max_length=50)            # № кабинета
    capacity = models.PositiveIntegerField(default=0) # вместимость
    computers = models.PositiveIntegerField(default=0)
    room_type = models.ForeignKey(RoomType, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ("building", "name")

    def __str__(self):
        return f"{self.building} · {self.name}"

class LessonType(models.Model):
    name = models.CharField(max_length=50)  # лекция, практика, зачёт, экзамен

    def __str__(self):
        return self.name

class Discipline(models.Model):
    title = models.CharField(max_length=200)

    # 👇 Новые поля
    DELIVERY_CHOICES = [
        ("in_person", "Очная"),
        ("remote", "Дистанционная"),
        ("mixed", "Смешанная"),  # можно и так, и так
    ]
    delivery_mode = models.CharField(max_length=16, choices=DELIVERY_CHOICES, default="in_person")

    default_lesson_type = models.ForeignKey(
        "LessonType", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Тип занятия по умолчанию (лекция/практика/лабораторная и т.д.)"
    )

    required_room_type = models.ForeignKey(
        "RoomType", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Если задан, дисциплина должна проводиться в аудитории этого типа"
    )

    requires_computers = models.BooleanField(
        default=False,
        help_text="Требуются компьютеры по числу студентов (для компьютерных дисциплин)"
    )

    def __str__(self):
        return self.title

class Teacher(models.Model):
    full_name = models.CharField(max_length=200)
    user = models.OneToOneField(           # 👈 НОВОЕ
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="teacher_profile"
    )

    def __str__(self):
        return self.full_name

class StudentGroup(models.Model):
    code = models.CharField(max_length=50, unique=True)  # например ИСП-31
    size = models.PositiveIntegerField(default=0)        # кол-во студентов
    department = models.CharField(max_length=120, blank=True)  # здание/отделение

    def __str__(self):
        return self.code

class TeacherWorkload(models.Model):
    teacher = models.OneToOneField(Teacher, on_delete=models.CASCADE, related_name="workload")
    weekly_hours_limit = models.PositiveSmallIntegerField(default=36)  # например
    # список дней без работы (0-пн ... 6-вс), храним строкой CSV для простоты MVP: "5,6"
    days_off = models.CharField(max_length=20, blank=True)
    # окно рабочего времени по умолчанию (на день)
    default_start = models.TimeField(null=True, blank=True)
    default_end = models.TimeField(null=True, blank=True)

class TeacherDayOverride(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="day_overrides")
    date = models.DateField()
    is_off = models.BooleanField(default=False)
    start = models.TimeField(null=True, blank=True)
    end = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ("teacher", "date")

class GroupDisciplinePlan(models.Model):
    group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE, related_name="plans")
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE)
    hours_total = models.PositiveSmallIntegerField()  # всего часов по предмету
    hours_assigned = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("group", "discipline")

class TeachingAssignment(models.Model):
    """Назначение: преподаватель ведёт дисциплину у группы."""
    group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE, related_name="assignments")
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name="assignments")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="assignments")

    class Meta:
        unique_together = ("group", "discipline", "teacher")

    def __str__(self):
        return f"{self.group} · {self.discipline} → {self.teacher}"

class Holiday(models.Model):
    """Нерабочий день/мероприятие."""
    date = models.DateField(unique=True)
    title = models.CharField(max_length=200, blank=True)
    is_working = models.BooleanField(default=False)  # true = всё-таки рабочий (исключение)

    def __str__(self):
        return f"{self.date} {'(раб.)' if self.is_working else '(выходной)'} {self.title}"

class BuildingPriority(models.Model):
    """
    Приоритет корпусов для группы/дисциплины.
    Чем МЕНЬШЕ priority, тем ВЫШЕ приоритет (0 — самый высокий).
    """
    group = models.ForeignKey("StudentGroup", on_delete=models.CASCADE, related_name="building_prefs")
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name="building_prefs")
    building = models.ForeignKey("Building", on_delete=models.CASCADE)
    priority = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("group", "discipline", "building")
        ordering = ["priority", "building__name"]

    def __str__(self):
        return f"{self.group.code} · {self.discipline.title} → {self.building.name} (#{self.priority})"