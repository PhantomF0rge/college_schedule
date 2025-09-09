#!/usr/bin/env python
import os, sys
from pathlib import Path
from datetime import time

# подготовка Django
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.db import transaction
from scheduleapp.models import TimeSlot

# целевое расписание звонков (Калининград)
BELL = [
    (1, time(8, 20),  time(9, 50)),
    (2, time(10, 0),  time(11, 30)),
    (3, time(11, 35), time(13, 5)),
    (4, time(13, 35), time(15, 5)),
    (5, time(15, 10), time(16, 40)),
    (6, time(16, 50), time(18, 20)),
    (7, time(18, 25), time(19, 55)),
    (8, time(20, 0),  time(21, 30)),
]

@transaction.atomic
def apply():
    kept_ids = []
    for order, start_t, end_t in BELL:
        obj, _ = TimeSlot.objects.get_or_create(order=order, defaults={
            "start_time": start_t,
            "end_time": end_t,
        })
        changed = (obj.start_time != start_t) or (obj.end_time != end_t)
        obj.start_time = start_t
        obj.end_time   = end_t
        obj.save(update_fields=["start_time", "end_time"])
        kept_ids.append(obj.id)
        print(f"[ok] {order} пара: {start_t.strftime('%H:%M')}–{end_t.strftime('%H:%M')} "
              f"{'(обновлено)' if changed else '(создано/актуально)'}")

    # удалить лишние слоты (если были)
    qs = TimeSlot.objects.exclude(id__in=kept_ids)
    removed = qs.count()
    if removed:
        qs.delete()
        print(f"[cleanup] Удалено лишних слотов: {removed}")

if __name__ == "__main__":
    apply()
    print("\nГотово. Проверь: /api/schedule/today/?group=ИСП-31")
