from datetime import datetime, timedelta
from django.http import JsonResponse, HttpResponseBadRequest
from django.db.models import Q
from django.db import transaction
from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from directory.models import (
    StudentGroup, Discipline, Teacher, Room, TeachingAssignment, Holiday, Building,
    GroupDisciplinePlan, TeacherWorkload, TeacherDayOverride, BuildingPriority, LessonType,
    RoomType
)
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from scheduleapp.models import Lesson, TimeSlot, HomeworkItem, Room
from urllib.parse import quote, unquote
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from directory.models import Room

COOKIE_NAME = "preferred_group"

def _is_admin(user):
    return user.is_staff or user.is_superuser or user.groups.filter(name="Admin").exists()

def _is_teacher(user):
    return user.is_authenticated and user.groups.filter(name="Teacher").exists()

def _get_logged_teacher(request):
    if not _is_teacher(request.user):
        return None
    from directory.models import Teacher
    return Teacher.objects.filter(user=request.user).first()

def _get_teacher_for_user(user):
    # 1) Явная связь OneToOne
    from directory.models import Teacher
    t = Teacher.objects.filter(user=user).first()
    if t:
        return t
    # 2) Фолбэк: попытка по ФИО (если ещё не привязили)
    full = (user.get_full_name() or "").strip()
    if full:
        return Teacher.objects.filter(full_name__iexact=full).first()
    return None

def badge_for(status, is_remote):
    if is_remote:
        return "remote"
    return {"ongoing": "ongoing", "upcoming": "upcoming", "past": "past"}.get(status, "past")

def _q(request, key="q"):
    return (request.GET.get(key) or "").strip()

def suggest_any(request):
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse([], safe=False)
    res = []

    for g in StudentGroup.objects.filter(code__icontains=q)[:5]:
        res.append({"type":"group","id":g.id,"label":g.code})
    for t in Teacher.objects.filter(full_name__icontains=q)[:5]:
        res.append({"type":"teacher","id":t.id,"label":t.full_name})
    for d in Discipline.objects.filter(title__icontains=q)[:5]:
        res.append({"type":"discipline","id":d.id,"label":d.title})

    return JsonResponse(res, safe=False)

def suggest_groups(request):
    q = _q(request)
    qs = StudentGroup.objects.filter(code__icontains=q)[:10] if q else StudentGroup.objects.none()
    return JsonResponse([{"id": g.id, "label": g.code} for g in qs], safe=False)

def suggest_teachers(request):
    q = _q(request)
    qs = Teacher.objects.filter(full_name__icontains=q)[:10] if q else Teacher.objects.none()
    return JsonResponse([{"id": t.id, "label": t.full_name} for t in qs], safe=False)

def suggest_disciplines(request):
    q = _q(request)
    qs = Discipline.objects.filter(title__icontains=q)[:10] if q else Discipline.objects.none()
    return JsonResponse([{"id": d.id, "label": d.title} for d in qs], safe=False)

def _json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return None

def _ok(data, status=200):
    return JsonResponse(data, status=status, safe=not isinstance(data, list))

def _err(msg, status=400):
    return JsonResponse({"error": msg}, status=status)

def _pick(d, keys):
    return {k: d[k] for k in keys if k in d}

def _list(model, values):
    return list(model.objects.values(*values))

from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from scheduleapp.models import Lesson, TimeSlot

def schedule_today(request):
    group_code = request.GET.get("group")
    teacher_id = request.GET.get("teacher")

    if not group_code and not teacher_id:
        return HttpResponseBadRequest("Нужно указать ?group=КОД_ГРУППЫ или ?teacher=ID")

    today = timezone.localdate()

    lessons_qs = (
        Lesson.objects
        .filter(date=today)
        .select_related("timeslot", "discipline", "teacher", "lesson_type", "room", "room__building")
        .select_related("homework")
    )

    if group_code:
        lessons_qs = lessons_qs.filter(group__code=group_code)
    if teacher_id:
        try:
            teacher_id = int(teacher_id)
        except ValueError:
            return HttpResponseBadRequest("teacher должен быть числом (ID преподавателя).")
        lessons_qs = lessons_qs.filter(teacher_id=teacher_id)

    slots = list(TimeSlot.objects.all().order_by("order"))
    lessons_by_slot = {l.timeslot_id: l for l in lessons_qs}

    schedule = []
    for slot in slots:
        lesson = lessons_by_slot.get(slot.id)
        time_str = f"{slot.start_time.strftime('%H:%M')}–{slot.end_time.strftime('%H:%M')}"
        if lesson:
            try:
                hw_text = lesson.homework.text
            except ObjectDoesNotExist:
                hw_text = None

            st = lesson.status_for_now()  # 👈 вычисляем статус один раз
            schedule.append({
            	"id": lesson.id,
                "order": slot.order,
                "time": time_str,
                "discipline": lesson.discipline.title,
                "teacher": lesson.teacher.full_name,
                "lesson_type": lesson.lesson_type.name,
                "room": lesson.room.name if lesson.room else None,
                "building": lesson.room.building.name if lesson.room else None,
                "is_remote": lesson.is_remote,
                "remote_platform": lesson.remote_platform,
                "status": st,                         # ongoing / upcoming / past
                "badge": badge_for(st, lesson.is_remote),  # 👈 добавили бейдж
                "homework": hw_text,
            })
        else:
            schedule.append({
                "order": slot.order,
                "time": time_str,
                "break": True
            })

    return JsonResponse(schedule, safe=False)

def schedule_period(request):
    """
    GET /api/schedule/period/?start=YYYY-MM-DD&end=YYYY-MM-DD&group=КОД | &teacher=ID
    Возвращает по дням: слоты с парами или 'перерывами'. 
    """
    group_code = request.GET.get("group")
    teacher_id = request.GET.get("teacher")
    start = request.GET.get("start")
    end = request.GET.get("end")

    if not (group_code or teacher_id):
        return HttpResponseBadRequest("Нужно указать ?group=КОД_ГРУППЫ или ?teacher=ID")
    if not (start and end):
        return HttpResponseBadRequest("Нужно указать ?start=YYYY-MM-DD и ?end=YYYY-MM-DD")

    try:
        start_date = timezone.datetime.fromisoformat(start).date()
        end_date = timezone.datetime.fromisoformat(end).date()
    except ValueError:
        return HttpResponseBadRequest("Неверный формат дат. Используйте YYYY-MM-DD.")

    if start_date > end_date:
        return HttpResponseBadRequest("start не может быть позже end.")

    lessons_qs = (
        Lesson.objects
        .filter(date__range=(start_date, end_date))
        .select_related("timeslot", "discipline", "teacher", "lesson_type", "room", "room__building")
        .select_related("homework")
    )
    if group_code:
        lessons_qs = lessons_qs.filter(group__code=group_code)
    if teacher_id:
        try:
            teacher_id = int(teacher_id)
        except ValueError:
            return HttpResponseBadRequest("teacher должен быть числом (ID преподавателя).")
        lessons_qs = lessons_qs.filter(teacher_id=teacher_id)

    slots = list(TimeSlot.objects.all().order_by("order"))
    # сгруппируем уроки по дате и по слоту
    lessons_map = {}
    for l in lessons_qs:
        lessons_map.setdefault(l.date, {})[l.timeslot_id] = l

    # формируем ответ по каждому дню
    result = []
    cur = start_date
    today = timezone.localdate()
    while cur <= end_date:
        day_items = []
        day_lessons_by_slot = lessons_map.get(cur, {})

        for slot in slots:
            lesson = day_lessons_by_slot.get(slot.id)
            time_str = f"{slot.start_time.strftime('%H:%M')}–{slot.end_time.strftime('%H:%M')}"
            if lesson:
                try:
                    hw_text = lesson.homework.text
                except ObjectDoesNotExist:
                    hw_text = None

                # статус относительно конкретного дня/времени
                if cur != today:
                    status = "past" if cur < today else "upcoming"
                else:
                    status = lesson.status_for_now()

                # внутри if lesson:
                day_items.append({
                	"id": lesson.id,
                    "order": slot.order,
                    "time": time_str,
                    "discipline": lesson.discipline.title,
                    "teacher": lesson.teacher.full_name,
                    "lesson_type": lesson.lesson_type.name,
                    "room": lesson.room.name if lesson.room else None,
                    "building": lesson.room.building.name if lesson.room else None,
                    "is_remote": lesson.is_remote,
                    "remote_platform": lesson.remote_platform,
                    "status": status,
                    "badge": badge_for(status, lesson.is_remote),  # 👈
                    "homework": hw_text,
                })
            else:
                day_items.append({
                    "order": slot.order,
                    "time": time_str,
                    "break": True
                })

        result.append({
            "date": cur.isoformat(),
            "items": day_items
        })
        cur += timedelta(days=1)

    return JsonResponse(result, safe=False)

def set_preferred_group(request):
    code = (request.GET.get("group") or "").strip()
    if not code:
        return HttpResponseBadRequest("Укажи ?group=КОД")
    if not StudentGroup.objects.filter(code=code).exists():
        return HttpResponseBadRequest("Группа не найдена")
    resp = JsonResponse({"ok": True, "group": code})
    enc = quote(code, safe="")  # 👈 ASCII-safe для заголовка
    resp.set_cookie(COOKIE_NAME, enc, max_age=60*60*24*365, samesite="Lax")
    return resp

def get_preferred_group(request):
    enc = request.COOKIES.get(COOKIE_NAME)
    code = unquote(enc) if enc else None  # 👈 обратно в человекочитаемый вид
    return JsonResponse({"group": code})

@login_required
@require_http_methods(["POST"])
def teacher_set_homework(request):
    if not _is_teacher(request.user):
        return HttpResponseBadRequest("Только для преподавателей.")
    lesson_id = request.POST.get("lesson_id")
    text = (request.POST.get("text") or "").strip()
    if not lesson_id or not text:
        return HttpResponseBadRequest("Нужно lesson_id и text.")
    # урок должен принадлежать текущему преподавателю
    t = _get_teacher_for_user(request.user)
    if not t:
        return HttpResponseBadRequest("Не найден профиль преподавателя для пользователя.")
    try:
        lesson = Lesson.objects.select_related("teacher").get(pk=lesson_id, teacher=t)
    except Lesson.DoesNotExist:
        return HttpResponseBadRequest("Пара не найдена или не ваша.")
    # создаём/обновляем ДЗ
    obj, _ = HomeworkItem.objects.update_or_create(lesson=lesson, defaults={"text": text})
    return JsonResponse({"ok": True, "lesson_id": lesson.id, "homework": obj.text})

@login_required
def teacher_free_rooms(request):
    """GET ?lesson_id=ID  -> список свободных аудиторий, подходящих по вместимости/ПК если известна группа."""
    if not _is_teacher(request.user):
        return HttpResponseBadRequest("Только для преподавателей.")
    lesson_id = request.GET.get("lesson_id")
    if not lesson_id:
        return HttpResponseBadRequest("Нужно lesson_id.")
    t = _get_teacher_for_user(request.user)
    if not t:
        return HttpResponseBadRequest("Не найден профиль преподавателя.")
    try:
        lesson = Lesson.objects.select_related("group").get(pk=lesson_id, teacher=t)
    except Lesson.DoesNotExist:
        return HttpResponseBadRequest("Пара не найдена или не ваша.")

    # Находим занятые комнаты в этот слот/дату
    busy_room_ids = Lesson.objects.filter(date=lesson.date, timeslot=lesson.timeslot, room__isnull=False)\
                                  .exclude(pk=lesson.pk).values_list("room_id", flat=True)

    qs = Room.objects.exclude(id__in=busy_room_ids)
    # фильтры по вместимости и ПК, если есть размер группы
    if lesson.group and lesson.group.size:
        qs = qs.filter(Q(capacity__gte=lesson.group.size) | Q(capacity=0))
        qs = qs.filter(Q(computers__gte=lesson.group.size) | Q(computers=0) | Q(computers__isnull=True))
    data = [{"id": r.id, "title": f"{r.building.name} · {r.name}", "capacity": r.capacity, "computers": r.computers} for r in qs.order_by("building__name","name")]
    return JsonResponse(data, safe=False)

@login_required
@require_http_methods(["POST"])
def teacher_change_room(request):
    """POST: lesson_id, room_id — сменить кабинет, если свободен и подходит (валидаторы Lesson.clean сработают)."""
    if not _is_teacher(request.user):
        return HttpResponseBadRequest("Только для преподавателей.")
    lesson_id = request.POST.get("lesson_id")
    room_id = request.POST.get("room_id")
    if not (lesson_id and room_id):
        return HttpResponseBadRequest("Нужно lesson_id и room_id.")
    t = _get_teacher_for_user(request.user)
    if not t:
        return HttpResponseBadRequest("Не найден профиль преподавателя.")
    try:
        lesson = Lesson.objects.get(pk=lesson_id, teacher=t)
    except Lesson.DoesNotExist:
        return HttpResponseBadRequest("Пара не найдена или не ваша.")

    from directory.models import Room
    try:
        room = Room.objects.get(pk=room_id)
    except Room.DoesNotExist:
        return HttpResponseBadRequest("Кабинет не найден.")

    # смена и валидация нашими правилами из Lesson.clean()
    lesson.is_remote = False
    lesson.room = room
    try:
        lesson.save()
    except ValidationError as e:
        return HttpResponseBadRequest("; ".join(sum(e.message_dict.values(), [])))

    return JsonResponse({"ok": True, "lesson_id": lesson.id, "room": room.name, "building": room.building.name})

@login_required
def teacher_me_schedule(request):
    """GET ?start=YYYY-MM-DD&end=YYYY-MM-DD — расписание текущего преподавателя по дням со слотами/перерывами."""
    t = _get_logged_teacher(request)
    if not t:
        return HttpResponseBadRequest("Не найден профиль преподавателя.")

    start = request.GET.get("start")
    end = request.GET.get("end")
    if not (start and end):
        return HttpResponseBadRequest("Нужно ?start и ?end (YYYY-MM-DD).")
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
    except ValueError:
        return HttpResponseBadRequest("Неверный формат дат.")

    slots = list(TimeSlot.objects.all().order_by("order"))
    lessons_qs = (
        Lesson.objects
        .filter(date__range=(start_date, end_date), teacher=t)
        .select_related("timeslot", "discipline", "group", "lesson_type", "room", "room__building")
        .select_related("homework")
    )
    lessons_map = {}
    for l in lessons_qs:
        lessons_map.setdefault(l.date, {})[l.timeslot_id] = l

    today = timezone.localdate()
    result = []
    cur = start_date
    while cur <= end_date:
        day_items = []
        day_map = lessons_map.get(cur, {})
        for slot in slots:
            lesson = day_map.get(slot.id)
            time_str = f"{slot.start_time.strftime('%H:%M')}–{slot.end_time.strftime('%H:%M')}"
            if lesson:
                try:
                    hw_text = lesson.homework.text
                except ObjectDoesNotExist:
                    hw_text = None

                status = ("past" if cur < today else "upcoming") if cur != today else lesson.status_for_now()
                day_items.append({
                    "id": lesson.id,
                    "order": slot.order,
                    "time": time_str,
                    "group": lesson.group.code,
                    "discipline": lesson.discipline.title,
                    "lesson_type": lesson.lesson_type.name,
                    "room": lesson.room.name if lesson.room else None,
                    "building": lesson.room.building.name if lesson.room else None,
                    "is_remote": lesson.is_remote,
                    "remote_platform": lesson.remote_platform,
                    "status": status,
                    "badge": badge_for(status, lesson.is_remote),
                    "homework": hw_text,
                })
            else:
                day_items.append({"order": slot.order, "time": time_str, "break": True})
        result.append({"date": cur.isoformat(), "items": day_items})
        cur += timedelta(days=1)

    return JsonResponse(result, safe=False)

@login_required
def teacher_me_stats(request):
    """GET ?start&end — агрегаты: количество пар, часов, рабочих дней."""
    t = _get_logged_teacher(request)
    if not t:
        return HttpResponseBadRequest("Не найден профиль преподавателя.")

    start = request.GET.get("start")
    end = request.GET.get("end")
    if not (start and end):
        return HttpResponseBadRequest("Нужно ?start и ?end (YYYY-MM-DD).")
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
    except ValueError:
        return HttpResponseBadRequest("Неверный формат дат.")

    qs = (
        Lesson.objects.filter(date__range=(start_date, end_date), teacher=t)
        .select_related("timeslot")
    )

    # считаем длительность слотов
    def minutes_for_slot(ts):
        dt_start = datetime.combine(start_date, ts.start_time)
        dt_end = datetime.combine(start_date, ts.end_time)
        return int((dt_end - dt_start).total_seconds() // 60)

    total_lessons = qs.count()
    total_minutes = sum(minutes_for_slot(l.timeslot) for l in qs)
    days_with_lessons = qs.values_list("date", flat=True).distinct().count()

    return JsonResponse({
        "total_lessons": total_lessons,
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 2),
        "working_days": days_with_lessons,
    })

@user_passes_test(_is_admin)
def admin_generate_schedule(request):
    """
    GET /api/admin/generate/?start=YYYY-MM-DD&end=YYYY-MM-DD&groups=КОД1,КОД2&dry_run=1&backtrack=1
    Улучшенный жадный генератор с мягким бэктрекингом, подробными конфликтами,
    учётом delivery_mode/required_room_type/компьютеров и приоритетов корпусов.
    """
    q_start = request.GET.get("start"); q_end = request.GET.get("end")
    dry_run = request.GET.get("dry_run", "1") != "0"
    backtrack = request.GET.get("backtrack", "1") != "0"  # NEW: включить бэктрекинг
    groups_csv = (request.GET.get("groups") or "").strip()

    if not (q_start and q_end):
        return HttpResponseBadRequest("Нужно ?start и ?end")
    try:
        start_date = datetime.fromisoformat(q_start).date()
        end_date = datetime.fromisoformat(q_end).date()
    except ValueError:
        return HttpResponseBadRequest("Неверный формат дат.")
    if start_date > end_date:
        return HttpResponseBadRequest("start>end")

    groups = list(StudentGroup.objects.filter(code__in=[s.strip() for s in groups_csv.split(",") if s.strip()])) if groups_csv else list(StudentGroup.objects.all())
    if not groups:
        return HttpResponseBadRequest("Не найдены группы.")

    slots = list(TimeSlot.objects.all().order_by("order"))

    # Подтянем дисциплины разом (с новыми полями)
    disciplines = Discipline.objects.select_related("default_lesson_type", "required_room_type")
    disc_map = {d.id: d for d in disciplines}

    # планы часов
    plans = {g.id: list(GroupDisciplinePlan.objects.filter(group=g).select_related("discipline")) for g in groups}

    # назначения преподавателей
    assignments = {}
    for g in groups:
        by_disc = {}
        for a in TeachingAssignment.objects.filter(group=g).select_related("discipline", "teacher"):
            by_disc.setdefault(a.discipline_id, []).append(a.teacher)
        assignments[g.id] = by_disc

    # приоритеты зданий
    building_prefs = {}
    for pref in BuildingPriority.objects.all().select_related("group", "discipline", "building"):
        building_prefs.setdefault((pref.group_id, pref.discipline_id), []).append(pref)

    holidays = {h.date: h for h in Holiday.objects.all()}
    workloads = {w.teacher_id: w for w in TeacherWorkload.objects.select_related("teacher")}
    overrides = {}
    for o in TeacherDayOverride.objects.all():
        overrides.setdefault((o.teacher_id, o.date), o)

    # существующие занятия в диапазоне
    existing = Lesson.objects.filter(date__range=(start_date, end_date))\
        .select_related("timeslot", "group", "teacher", "room")
    busy_room = set((l.date, l.timeslot_id, l.room_id) for l in existing if l.room_id)
    busy_teacher = set((l.date, l.timeslot_id, l.teacher_id) for l in existing)
    busy_group = set((l.date, l.timeslot_id, l.group_id) for l in existing)

    rooms_all = list(Room.objects.select_related("building", "room_type").order_by("capacity", "computers", "building__name", "name"))

    # вспомогалки
    ACADEMIC_MIN = getattr(settings, "ACADEMIC_MINUTES", 45)

    def slot_minutes(ts: TimeSlot):
        d0 = datetime.combine(start_date, ts.start_time)
        d1 = datetime.combine(start_date, ts.end_time)
        return int((d1 - d0).total_seconds() // 60)

    def slot_to_academic_hours(ts: TimeSlot):
        return slot_minutes(ts) / ACADEMIC_MIN

    def teacher_allowed_on_day(t: Teacher, day):
        h = holidays.get(day)
        if h and not h.is_working:
            return False
        ov = overrides.get((t.id, day))
        if ov:
            return not ov.is_off
        w = workloads.get(t.id)
        if not w or not w.days_off:
            return True
        offs = {int(x) for x in w.days_off.split(",") if x.strip().isdigit()}
        return (day.weekday() not in offs)

    def teacher_time_window_ok(t: Teacher, slot: TimeSlot, day):
        w = workloads.get(t.id)
        ov = overrides.get((t.id, day))
        start = ov.start if ov and ov.start else (w.default_start if w and w.default_start else None)
        end = ov.end if ov and ov.end else (w.default_end if w and w.default_end else None)
        if start and slot.start_time < start: return False
        if end and slot.end_time > end: return False
        return True

    weekly_minutes = {}
    for l in existing:
        wkey = (l.teacher_id, *l.date.isocalendar()[:2])
        weekly_minutes[wkey] = weekly_minutes.get(wkey, 0) + slot_minutes(l.timeslot)

    # подберём комнаты с учётом типа, компьютеров и приоритетов корпусов
    def candidate_rooms_for(group, disc: Discipline, day, slot):
        need_type = disc.required_room_type_id
        need_computers = disc.requires_computers
        gsize = group.size or 0

        # если дисциплина дистанционная — без кабинета
        if disc.delivery_mode == "remote":
            return []  # «нет комнат» как признак дистанта

        # смешанный/очный — выбираем аудитории
        cand = []
        for r in rooms_all:
            if (day, slot.id, r.id) in busy_room:
                continue
            if need_type and (r.room_type_id != need_type):
                continue
            # вместимость
            if r.capacity and gsize and r.capacity < gsize:
                continue
            # компьютеры
            if need_computers:
                if not r.computers or r.computers < gsize:
                    continue
            cand.append(r)

        # приоритет корпусов: (group, discipline) → отсортируем по BuildingPriority
        prefs = building_prefs.get((group.id, disc.id))
        if prefs:
            order_map = {p.building_id: p.priority for p in prefs}
            cand.sort(key=lambda r: (order_map.get(r.building_id, 9999), r.capacity or 0, r.computers or 0))
        else:
            # дефолт: минимально подходящая вместимость, затем компьютеры
            cand.sort(key=lambda r: (r.capacity or 9999, r.computers or 9999, r.building.name, r.name))

        return cand

    def pick_default_lessontype(disc: Discipline):
        return disc.default_lesson_type

    # подробные конфликты
    conflicts = []
    proposals = []
    stats = {"placed": 0, "skipped": 0}

    def add_conflict(reason, *, date, slot, group=None, discipline=None, teacher=None, room=None, details=None):
        conflicts.append({
            "reason": reason,
            "date": date.isoformat(),
            "slot": slot.order,
            "time": f"{slot.start_time.strftime('%H:%M')}–{slot.end_time.strftime('%H:%M')}",
            "group": getattr(group, "code", None),
            "discipline": getattr(discipline, "title", None),
            "teacher": getattr(teacher, "full_name", None),
            "room": getattr(room, "name", None),
            "room_building": getattr(getattr(room, "building", None), "name", None),
            "links": {
                # ссылки в админку
                "group": f"/admin/directory/studentgroup/{getattr(group,'id',0)}/change/" if group else None,
                "discipline": f"/admin/directory/discipline/{getattr(discipline,'id',0)}/change/" if discipline else None,
                "teacher": f"/admin/directory/teacher/{getattr(teacher,'id',0)}/change/" if teacher else None,
                "room": f"/admin/directory/room/{getattr(room,'id',0)}/change/" if room else None,
            },
            "details": details,
        })

    # МЯГКИЙ БЭКТРЕКИНГ: попытка переставить на соседний слот в тот же день (вниз), если конфликт
    def try_place(group, p_item, day, slot, try_shift=True):
        """
        p_item: плановая запись { 'plan': GroupDisciplinePlan, 'discipline': Discipline }
        """
        disc = p_item["discipline"]
        plan = p_item["plan"]

        # дистанционный курс — без аудитории
        is_remote = (disc.delivery_mode == "remote")
        # смешанный допускает любую доставку; начнём с очной (если есть аудитории), потом удалённо
        try_remote_as_fallback = (disc.delivery_mode == "mixed")

        # выберем преподавателя
        teachers = assignments.get(group.id, {}).get(disc.id, [])
        t_ok = None
        for t in teachers:
            if (day, slot.id, t.id) in busy_teacher:
                continue
            if not teacher_allowed_on_day(t, day):
                continue
            if not teacher_time_window_ok(t, slot, day):
                continue
            # недельный лимит — в минутах
            wk = (t.id, *day.isocalendar()[:2])
            limit = workloads.get(t.id).weekly_hours_limit * 60 if workloads.get(t.id) and workloads.get(t.id).weekly_hours_limit else None
            new_total = weekly_minutes.get(wk, 0) + slot_minutes(slot)
            if limit and new_total > limit:
                continue
            t_ok = t
            break
        if not t_ok:
            add_conflict("no_teacher", date=day, slot=slot, group=group, discipline=disc,
                         details="Нет доступного преподавателя (время/лимит/занятость)")
            return False

        # если очный/смешанный — попробуем комнату
        rooms_try = [] if is_remote else candidate_rooms_for(group, disc, day, slot)
        chosen_room = None
        chosen_remote = is_remote

        if not is_remote:
            for r in rooms_try:
                if (day, slot.id, r.id) in busy_room:
                    continue
                chosen_room = r
                break

            if not chosen_room and try_remote_as_fallback:
                # смешанная дисциплина — провалим в дистанционную форму
                chosen_remote = True

        # если и очное нельзя, и дистант не разрешён — конфликт (с опцией сдвига)
        if not chosen_remote and chosen_room is None:
            if try_shift:
                return False  # пусть вызвавший код попробует иной слот
            add_conflict("no_room", date=day, slot=slot, group=group, discipline=disc,
                         teacher=t_ok, details="Нет подходящей аудитории: тип/вместимость/ПК/занятость")
            return False

        # ок — фиксируем
        proposals.append({
            "date": day.isoformat(),
            "timeslot_id": slot.id,
            "group_id": group.id,
            "discipline_id": disc.id,
            "teacher_id": t_ok.id,
            "lesson_type_id": (pick_default_lessontype(disc).id if pick_default_lessontype(disc) else None),
            "room_id": (None if chosen_remote else (chosen_room.id if chosen_room else None)),
            "is_remote": chosen_remote,
        })

        # занятости и счётчики
        busy_group.add((day, slot.id, group.id))
        busy_teacher.add((day, slot.id, t_ok.id))
        if not chosen_remote and chosen_room:
            busy_room.add((day, slot.id, chosen_room.id))
        wk = (t_ok.id, *day.isocalendar()[:2])
        weekly_minutes[wk] = weekly_minutes.get(wk, 0) + slot_minutes(slot)

        # списываем часы из плана по длительности слота (в акад. часах)
        plan.hours_assigned += slot_to_academic_hours(slot)

        return True

    # основной проход
    cur = start_date
    while cur <= end_date:
        if (hol := holidays.get(cur)) and not hol.is_working:
            cur += timedelta(days=1); continue

        for slot in slots:
            for g in groups:
                if (cur, slot.id, g.id) in busy_group:
                    continue

                # выбери первую дисциплину с остатком часов
                p_items = plans.get(g.id, [])
                # сортировка: дисциплины с required_room_type/ПК — выше приоритета (их сложнее поставить)
                p_items.sort(key=lambda x: (
                    0 if (disc_map[x.discipline_id].required_room_type_id or disc_map[x.discipline_id].requires_computers) else 1
                ))
                candidate = None
                for p in p_items:
                    if p.hours_assigned < p.hours_total:
                        candidate = {"plan": p, "discipline": disc_map[p.discipline_id]}
                        break
                if not candidate:
                    continue

                placed = try_place(g, candidate, cur, slot, try_shift=backtrack)
                if not placed and backtrack:
                    # попробуем соседний слот ниже в этот день
                    next_slot = next((s for s in slots if s.order > slot.order), None)
                    if next_slot and (cur, next_slot.id, g.id) not in busy_group:
                        placed2 = try_place(g, candidate, cur, next_slot, try_shift=False)
                        if not placed2:
                            add_conflict("backtrack_failed", date=cur, slot=slot, group=g,
                                         discipline=candidate["discipline"],
                                         details="Перестановка на следующий слот не помогла")
                            stats["skipped"] += 1
                        else:
                            stats["placed"] += 1
                    else:
                        add_conflict("no_slot_to_shift", date=cur, slot=slot, group=g,
                                     discipline=candidate["discipline"],
                                     details="Нет следующего свободного слота для группы")
                        stats["skipped"] += 1
                elif placed:
                    stats["placed"] += 1
                else:
                    stats["skipped"] += 1

        cur += timedelta(days=1)

    if dry_run:
        # человекочитаемый превью
        pretty = []
        for p in proposals:
            ts = next(s for s in slots if s.id == p["timeslot_id"])
            g = next(gr for gr in groups if gr.id == p["group_id"])
            d = disc_map[p["discipline_id"]]
            t = Teacher.objects.get(pk=p["teacher_id"])
            room_text = "Дистанционно" if p["is_remote"] else (
                (lambda rid: (f"{Room.objects.get(pk=rid).building.name} · {Room.objects.get(pk=rid).name}") if rid else None)(p["room_id"])
            )
            pretty.append({
                "date": p["date"],
                "slot": ts.order,
                "time": f"{ts.start_time.strftime('%H:%M')}–{ts.end_time.strftime('%H:%M')}",
                "group": g.code,
                "discipline": d.title,
                "teacher": t.full_name,
                "room": room_text,
                "delivery": d.delivery_mode,
                "type": d.default_lesson_type.name if d.default_lesson_type_id else None
            })
        return JsonResponse({"dry_run": True, "proposals": pretty, "conflicts": conflicts, "stats": stats}, safe=False)

    # применение
    with transaction.atomic():
        to_create = []
        for p in proposals:
            ts = next(s for s in slots if s.id == p["timeslot_id"])
            lt = LessonType.objects.filter(pk=p["lesson_type_id"]).first()
            to_create.append(Lesson(
                date=datetime.fromisoformat(p["date"]).date(),
                timeslot=ts,
                group_id=p["group_id"],
                discipline_id=p["discipline_id"],
                teacher_id=p["teacher_id"],
                lesson_type=lt,
                room_id=p["room_id"],
                is_remote=p["is_remote"],
                remote_platform=("Moodle" if p["is_remote"] else ""),  # при желании выбирайте платформу
            ))
        Lesson.objects.bulk_create(to_create, batch_size=200)

        # обновим планы
        all_plans = []
        for glist in plans.values():
            all_plans.extend(glist)
        GroupDisciplinePlan.objects.bulk_update(all_plans, ["hours_assigned"], batch_size=200)

    return JsonResponse({"dry_run": False, "created": len(proposals), "conflicts": conflicts, "stats": stats})

@login_required
@user_passes_test(_is_admin)
def admin_list_groups(request):
    """Отдаёт все группы для мультиселекта администратора."""
    groups = StudentGroup.objects.order_by("department", "code").values("id", "code", "department")
    return JsonResponse(list(groups), safe=False)

@login_required
@user_passes_test(_is_admin)
def admin_list_teachers(request):
    qs = Teacher.objects.order_by("full_name").values("id","full_name")
    return JsonResponse(list(qs), safe=False)

@login_required
@user_passes_test(_is_admin)
def admin_teacher_schedule(request):
    """
    GET /api/admin/teacher/schedule/?teacher_id=ID&start=YYYY-MM-DD&end=YYYY-MM-DD
    Возвращает по дням расписание преподавателя: слоты с парами/перерывами.
    """
    tid = request.GET.get("teacher_id")
    start = request.GET.get("start")
    end = request.GET.get("end")
    if not (tid and start and end):
        return HttpResponseBadRequest("Нужно ?teacher_id, ?start, ?end")

    try:
        tid = int(tid)
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
    except ValueError:
        return HttpResponseBadRequest("Неверные параметры")

    slots = list(TimeSlot.objects.all().order_by("order"))
    lessons_qs = (
        Lesson.objects
        .filter(date__range=(start_date, end_date), teacher_id=tid)
        .select_related("timeslot","discipline","group","lesson_type","room","room__building")
        .select_related("homework")
    )
    # карта: дата -> {slot_id: lesson}
    by_day = {}
    for l in lessons_qs:
        by_day.setdefault(l.date, {})[l.timeslot_id] = l

    today = timezone.localdate()
    result = []
    cur = start_date
    while cur <= end_date:
        items = []
        day_map = by_day.get(cur, {})
        for slot in slots:
            l = day_map.get(slot.id)
            tstr = f"{slot.start_time.strftime('%H:%M')}–{slot.end_time.strftime('%H:%M')}"
            if l:
                try:
                    hw = l.homework.text
                except ObjectDoesNotExist:
                    hw = None
                status = ("past" if cur < today else "upcoming") if cur != today else l.status_for_now()
                items.append({
                    "id": l.id,
                    "order": slot.order,
                    "time": tstr,
                    "group": l.group.code,
                    "discipline": l.discipline.title,
                    "lesson_type": l.lesson_type.name if l.lesson_type else None,
                    "room": l.room.name if l.room else None,
                    "building": l.room.building.name if l.room else None,
                    "is_remote": l.is_remote,
                    "remote_platform": l.remote_platform,
                    "status": status,
                    "badge": badge_for(status, l.is_remote),
                    "homework": hw,
                })
            else:
                items.append({"order": slot.order, "time": tstr, "break": True})
        result.append({"date": cur.isoformat(), "items": items})
        cur += timedelta(days=1)

    return JsonResponse(result, safe=False)

@login_required
@user_passes_test(_is_admin)
def admin_schedule_period_all(request):
    """
    GET /api/admin/schedule/period_all/?start=YYYY-MM-DD&end=YYYY-MM-DD
    Плоский список занятий всех групп за период, с ключевыми полями.
    Удобно для админ-обзора и экспорта.
    """
    start = request.GET.get("start")
    end = request.GET.get("end")
    if not (start and end):
        return HttpResponseBadRequest("Нужно ?start и ?end")
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
    except ValueError:
        return HttpResponseBadRequest("Неверный формат дат")

    lessons = (
        Lesson.objects.filter(date__range=(start_date, end_date))
        .select_related("timeslot","group","discipline","teacher","lesson_type","room","room__building")
    )

    today = timezone.localdate()
    rows = []
    for l in lessons.order_by("date","timeslot__order","group__code"):
        status = ("past" if l.date < today else "upcoming") if l.date != today else l.status_for_now()
        rows.append({
            "id": l.id,
            "date": l.date.isoformat(),
            "slot": l.timeslot.order,
            "time": f"{l.timeslot.start_time.strftime('%H:%M')}–{l.timeslot.end_time.strftime('%H:%M')}",
            "group": l.group.code,
            "discipline": l.discipline.title,
            "teacher": l.teacher.full_name,
            "lesson_type": l.lesson_type.name if l.lesson_type else None,
            "room": l.room.name if l.room else None,
            "building": l.room.building.name if l.room else None,
            "is_remote": l.is_remote,
            "remote_platform": l.remote_platform,
            "status": status,
            "badge": badge_for(status, l.is_remote),
        })

    return JsonResponse(rows, safe=False)

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_teachers(request):
    if request.method == "GET":
        return _ok(_list(Teacher, ["id","full_name"]))
    data = _json(request)
    if data is None: return _err("invalid json")
    t = Teacher.objects.create(full_name=data.get("full_name","").strip())
    return _ok(model_to_dict(t))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["PATCH","DELETE"])
def studio_teachers_item(request, pk):
    try: t = Teacher.objects.get(pk=pk)
    except Teacher.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE":
        t.delete(); return _ok({"ok": True})
    data = _json(request)
    if data is None: return _err("invalid json")
    if "full_name" in data: t.full_name = data["full_name"].strip()
    t.save(); return _ok(model_to_dict(t))

# Buildings
@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_buildings(request):
    if request.method == "GET":
        return _ok(_list(Building, ["id","name"]))
    data = _json(request)
    if data is None: return _err("invalid json")
    b = Building.objects.create(name=data.get("name","").strip())
    return _ok(model_to_dict(b))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["PATCH","DELETE"])
def studio_buildings_item(request, pk):
    try: b = Building.objects.get(pk=pk)
    except Building.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE":
        b.delete(); return _ok({"ok": True})
    data = _json(request) or {}
    if "name" in data: b.name = data["name"].strip()
    b.save(); return _ok(model_to_dict(b))

# Rooms
@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_rooms(request):
    if request.method == "GET":
        rows = list(Room.objects.select_related("building","room_type").values(
            "id","name","capacity","computers","building_id","building__name","room_type_id","room_type__name"
        ))
        return _ok(rows)
    data = _json(request) or {}
    try:
        r = Room.objects.create(
            name=data.get("name","").strip(),
            building_id=int(data["building_id"]) if "building_id" in data else None,
            room_type_id=int(data["room_type_id"]) if "room_type_id" in data else None,
            capacity=int(data.get("capacity") or 0),
            computers=int(data.get("computers") or 0),
        )
        return _ok(model_to_dict(r))
    except Exception as e:
        return _err(str(e))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["PATCH","DELETE"])
def studio_rooms_item(request, pk):
    try: r = Room.objects.get(pk=pk)
    except Room.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE": r.delete(); return _ok({"ok": True})
    data = _json(request) or {}
    for f in ["name","building_id","room_type_id","capacity","computers"]:
        if f in data:
            setattr(r, f, data[f] if f in ["name"] else int(data[f] or 0))
    r.save(); return _ok(model_to_dict(r))

# Groups
@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_groups(request):
    if request.method == "GET":
        return _ok(_list(StudentGroup, ["id","code","size","department"]))
    data = _json(request) or {}
    g = StudentGroup.objects.create(
        code=data.get("code","").strip(),
        size=int(data.get("size") or 0),
        department=data.get("department","").strip() or None
    )
    return _ok(model_to_dict(g))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["PATCH","DELETE"])
def studio_groups_item(request, pk):
    try: g = StudentGroup.objects.get(pk=pk)
    except StudentGroup.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE": g.delete(); return _ok({"ok": True})
    data = _json(request) or {}
    for f in ["code","department"]:
        if f in data: setattr(g, f, data[f].strip())
    for f in ["size"]:
        if f in data: setattr(g, f, int(data[f] or 0))
    g.save(); return _ok(model_to_dict(g))

# Disciplines
@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_disciplines(request):
    if request.method == "GET":
        rows = list(Discipline.objects.select_related("default_lesson_type","required_room_type").values(
            "id","title","delivery_mode","default_lesson_type_id","required_room_type_id","requires_computers"
        ))
        return _ok(rows)
    data = _json(request) or {}
    d = Discipline.objects.create(
        title=data.get("title","").strip(),
        delivery_mode=data.get("delivery_mode") or "in_person",
        default_lesson_type_id=data.get("default_lesson_type_id"),
        required_room_type_id=data.get("required_room_type_id"),
        requires_computers=bool(data.get("requires_computers")),
    )
    return _ok(model_to_dict(d))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["PATCH","DELETE"])
def studio_disciplines_item(request, pk):
    try: d = Discipline.objects.get(pk=pk)
    except Discipline.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE": d.delete(); return _ok({"ok": True})
    data = _json(request) or {}
    for f in ["title","delivery_mode"]:
        if f in data: setattr(d, f, data[f] if f!="title" else data[f].strip())
    for f in ["default_lesson_type_id","required_room_type_id"]:
        if f in data: setattr(d, f, data[f] or None)
    if "requires_computers" in data: d.requires_computers = bool(data["requires_computers"])
    d.save(); return _ok(model_to_dict(d))

# LessonTypes
@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_lessontypes(request):
    if request.method == "GET":
        return _ok(_list(LessonType, ["id","name"]))
    data = _json(request) or {}
    lt = LessonType.objects.create(name=data.get("name","").strip())
    return _ok(model_to_dict(lt))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["PATCH","DELETE"])
def studio_lessontypes_item(request, pk):
    try: lt = LessonType.objects.get(pk=pk)
    except LessonType.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE": lt.delete(); return _ok({"ok": True})
    data = _json(request) or {}
    if "name" in data: lt.name = data["name"].strip()
    lt.save(); return _ok(model_to_dict(lt))

# TeachingAssignments
@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_assignments(request):
    if request.method == "GET":
        rows = list(TeachingAssignment.objects.select_related("group","discipline","teacher").values(
            "id","group_id","group__code","discipline_id","discipline__title","teacher_id","teacher__full_name"
        ))
        return _ok(rows)
    data = _json(request) or {}
    try:
        a = TeachingAssignment.objects.create(
            group_id=int(data["group_id"]),
            discipline_id=int(data["discipline_id"]),
            teacher_id=int(data["teacher_id"]),
        )
        return _ok(model_to_dict(a))
    except IntegrityError:
        return _err("Назначение уже существует")
    except Exception as e:
        return _err(str(e))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["DELETE","PATCH"])
def studio_assignments_item(request, pk):
    try: a = TeachingAssignment.objects.get(pk=pk)
    except TeachingAssignment.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE": a.delete(); return _ok({"ok": True})
    data = _json(request) or {}
    for f in ["group_id","discipline_id","teacher_id"]:
        if f in data: setattr(a, f, int(data[f]))
    a.save(); return _ok(model_to_dict(a))

# Plans (GroupDisciplinePlan)
@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_plans(request):
    if request.method == "GET":
        rows = list(GroupDisciplinePlan.objects.select_related("group","discipline").values(
            "id","group_id","group__code","discipline_id","discipline__title","hours_total","hours_assigned"
        ))
        return _ok(rows)
    data = _json(request) or {}
    p = GroupDisciplinePlan.objects.create(
        group_id=int(data["group_id"]),
        discipline_id=int(data["discipline_id"]),
        hours_total=float(data.get("hours_total") or 0),
        hours_assigned=float(data.get("hours_assigned") or 0),
    )
    return _ok(model_to_dict(p))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["PATCH","DELETE"])
def studio_plans_item(request, pk):
    try: p = GroupDisciplinePlan.objects.get(pk=pk)
    except GroupDisciplinePlan.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE": p.delete(); return _ok({"ok": True})
    data = _json(request) or {}
    for f in ["group_id","discipline_id"]:
        if f in data: setattr(p, f, int(data[f]))
    for f in ["hours_total","hours_assigned"]:
        if f in data: setattr(p, f, float(data[f] or 0))
    p.save(); return _ok(model_to_dict(p))

# Lessons (расписание)
@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET","POST"])
def studio_lessons(request):
    if request.method == "GET":
        rows = list(Lesson.objects.select_related("group","discipline","teacher","lesson_type","room","room__building","timeslot")
            .values("id","date","timeslot_id","timeslot__order","group_id","group__code","discipline_id","discipline__title",
                    "teacher_id","teacher__full_name","lesson_type_id","lesson_type__name","room_id","room__name","room__building__name",
                    "is_remote","remote_platform"))
        return _ok(rows)
    data = _json(request) or {}
    try:
        with transaction.atomic():
            l = Lesson.objects.create(
                date=parse_date(data["date"]),
                timeslot_id=int(data["timeslot_id"]),
                group_id=int(data["group_id"]),
                discipline_id=int(data["discipline_id"]),
                teacher_id=int(data["teacher_id"]),
                lesson_type_id=(int(data["lesson_type_id"]) if data.get("lesson_type_id") else None),
                room_id=(int(data["room_id"]) if data.get("room_id") else None),
                is_remote=bool(data.get("is_remote")),
                remote_platform=data.get("remote_platform","").strip()
            )
        return _ok(model_to_dict(l))
    except Exception as e:
        return _err(str(e))

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["PATCH","DELETE"])
def studio_lessons_item(request, pk):
    try: l = Lesson.objects.get(pk=pk)
    except Lesson.DoesNotExist: return _err("not found", 404)
    if request.method == "DELETE":
        l.delete(); return _ok({"ok": True})
    data = _json(request) or {}
    if "date" in data: l.date = parse_date(data["date"])
    for f in ["timeslot_id","group_id","discipline_id","teacher_id","lesson_type_id","room_id"]:
        if f in data: setattr(l, f, (int(data[f]) if data[f] else None))
    if "is_remote" in data: l.is_remote = bool(data["is_remote"])
    if "remote_platform" in data: l.remote_platform = data["remote_platform"].strip()
    l.save(); return _ok(model_to_dict(l))

@login_required
@user_passes_test(_is_admin)
def studio_options(request):
    """Справочники для селектов на странице Студии."""
    data = {
        "buildings":   list(Building.objects.values("id","name").order_by("name")),
        "room_types":  list(RoomType.objects.values("id","name").order_by("name")),
        "rooms":       list(Room.objects.select_related("building").values("id","name","building_id","building__name").order_by("building__name","name")),
        "groups":      list(StudentGroup.objects.values("id","code").order_by("code")),
        "teachers":    list(Teacher.objects.values("id","full_name").order_by("full_name")),
        "disciplines": list(Discipline.objects.values("id","title").order_by("title")),
        "lesson_types":list(LessonType.objects.values("id","name").order_by("name")),
        "timeslots":   list(TimeSlot.objects.values("id","order","start_time","end_time").order_by("order")),
    }
    return JsonResponse(data)