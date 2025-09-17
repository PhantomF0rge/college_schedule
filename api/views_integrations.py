# api/views_integrations.py
from __future__ import annotations
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET
from django.contrib.admin.views.decorators import staff_member_required
from .services.ranepa import fetch_week_from_ranepa, norm

@staff_member_required
@require_GET
def ranepa_conflicts(request: HttpRequest):
    kind  = request.GET.get("kind","group")
    q     = request.GET.get("q","")
    sem   = int(request.GET.get("sem","1") or 1)
    start = request.GET.get("start")  # ISO ПН
    end   = request.GET.get("end")

    items = fetch_week_from_ranepa(q=q, kind=kind, sem=sem, start=start, end=end)

    # Проставим временные слоты (если в системе есть)
    tsmap = {}
    try:
        # пример: подтянуть звонки из вашей студии (если есть такой сервис)
        from .services.studio import get_timeslots_map  # {order: "HH:MM–HH:MM"}
        tsmap = get_timeslots_map()
    except Exception:
        pass

    def tr(order: int | None):
        if order is None: return None, None
        s = tsmap.get(order)
        if not s: return None, None
        import re
        m = re.search(r"(\d{1,2}):(\d{2}).*?(\d{1,2}):(\d{2})", s)
        if not m: return None, None
        return f"{int(m.group(1)):02d}:{m.group(2)}", f"{int(m.group(3)):02d}:{m.group(4)}"

    # Группируем по дате, потом проверяем накладки для: group, teacher, room
    from collections import defaultdict
    by_date = defaultdict(list)
    for it in items:
        start_hm, end_hm = tr(it.get("order"))
        by_date[it["date"]].append({
            **it, "start": start_hm, "end": end_hm
        })

    def overlap(a_start, a_end, b_start, b_end):
        # если нет времени — считаем, что одна и та же пара (order) конфликтует
        if not a_start or not b_start:
            return True
        return not (a_end <= b_start or b_end <= a_start)

    conflicts = []
    for day, arr in by_date.items():
        n = len(arr)
        for i in range(n):
            A = arr[i]
            for j in range(i+1, n):
                B = arr[j]
                if not overlap(A["start"], A["end"], B["start"], B["end"]):
                    continue
                reasons = []
                if A.get("group") and B.get("group") and norm(A["group"]).lower()==norm(B["group"]).lower():
                    reasons.append("Одинаковая группа в одно время")
                if A.get("teacher") and B.get("teacher") and norm(A["teacher"]).lower()==norm(B["teacher"]).lower():
                    reasons.append("Преподаватель занят в другое занятие")
                if not A.get("is_remote") and not B.get("is_remote"):
                    r1, r2 = (A.get("room") or "").strip(), (B.get("room") or "").strip()
                    if r1 and r2 and r1==r2:
                        reasons.append("Одна и та же аудитория")
                if reasons:
                    conflicts.append({
                        "date": day,
                        "a": A, "b": B,
                        "reasons": reasons,
                    })

    return JsonResponse({"conflicts": conflicts})
