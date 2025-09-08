#!/usr/bin/env python
import os, sys, argparse
from pathlib import Path
from contextlib import suppress

# === ДОБАВЛЕНО: положить корень проекта в sys.path ===
BASE_DIR = Path(__file__).resolve().parents[1]   # .../college_schedule
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# если у тебя модуль настроек называется иначе — поменяй ниже
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.apps import apps
from django.db import transaction

def get_model(label):
    with suppress(LookupError):
        return apps.get_model(label)
    return None

def count(model):
    try:
        return model.objects.count()
    except Exception:
        return 0

def wipe_models(labels, dry_run=False):
    total = 0
    for label in labels:
        model = get_model(label)
        if not model:
            print(f"[skip] Нет модели {label}")
            continue
        n = count(model)
        if dry_run:
            print(f"[dry]  {label:35}  будет удалено: {n}")
        else:
            deleted = model.objects.all().delete()
            print(f"[del]  {label:35}  удалено записей: {n}")
        total += n
    return total

def main():
    parser = argparse.ArgumentParser(
        description="Очистка данных расписания: уроки, группы, преподы, предметы, аудитории и т.п."
    )
    parser.add_argument("--yes", action="store_true",
                        help="подтверждаю удаление данных")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать, что будет удалено, но НЕ удалять")
    parser.add_argument("--wipe-timeslots", action="store_true",
                        help="дополнительно удалить звонки (TimeSlot)")
    args = parser.parse_args()

    if not args.yes and not args.dry_run:
        print("⚠️  Добавь --yes чтобы выполнить удаление, либо --dry-run для прогона без удаления.")
        sys.exit(1)

    # Порядок важен: сначала зависимости (уроки/дз/журналы), потом справочники.
    models_phase1 = [
        "scheduleapp.Homework",         # если есть
        "scheduleapp.Lesson",
        "scheduleapp.ImportJob",        # журнал импортов (если используете)
    ]

    # справочники расписания/каталоги
    models_phase2 = [
        "directory.PlanAssignment",     # если есть
        "directory.PlanItem",
        "directory.StudyPlan",
        "directory.TeacherWorkload",
        "directory.DisciplineHours",
        "directory.LessonType",
        "directory.Room",               # комнаты до Building (FK)
        "directory.Building",
        "directory.RoomType",
        "directory.Discipline",
        "directory.Teacher",
        "directory.StudentGroup",
    ]

    # необязательно: удалить звонки
    timeslot_labels = ["scheduleapp.TimeSlot"]

    print("=== Фаза 1: зависимые объекты (уроки/дз/логи) ===")
    with transaction.atomic():
        wipe_models(models_phase1, dry_run=args.dry_run)

    print("\n=== Фаза 2: справочники ===")
    with transaction.atomic():
        wipe_models(models_phase2, dry_run=args.dry_run)

    if args.wipe_timeslots:
        print("\n=== Дополнительно: TimeSlot (звонки) ===")
        with transaction.atomic():
            wipe_models(timeslot_labels, dry_run=args.dry_run)

    print("\nГотово.")

if __name__ == "__main__":
    main()
