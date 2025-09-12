# api/services/ranepa.py
import re
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup

BASE = "https://zf-ranepa-rasp.ru"

MONTH_SLUGS = {
    1:"jan", 2:"feb", 3:"mar", 4:"apr", 5:"may", 6:"jun",
    7:"jul", 8:"aug", 9:"sep", 10:"oct", 11:"nov", 12:"dec"
}
RU_DAYS = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]
RU_DAY_TO_IDX = {d:i for i,d in enumerate(RU_DAYS)}

WS = re.compile(r"^(?:\s*(?:<br\s*/?>|\n|\r)+\s*)+")
def norm(s: str | None) -> str:
    """Убираем \n, \r, \t, неразрывные пробелы и схлопываем до одного пробела."""
    return WS.sub(" ", (s or "").replace("\xa0", " ")).strip()

def _week_slug(start_iso: str) -> str:
    """RANEPA-неделя всегда ПН–СБ: строим slug вида sep08-sep13 от понедельника."""
    s = datetime.fromisoformat(start_iso).date()
    e = s + timedelta(days=5)  # суббота
    return f"{MONTH_SLUGS[s.month]}{s.day:02d}-{MONTH_SLUGS[e.month]}{e.day:02d}"

def _get(url: str) -> str:
    with httpx.Client(headers={"User-Agent":"Mozilla/5.0"}) as cli:
        r = cli.get(url, timeout=30)
        r.raise_for_status()
        return r.text

def _parse_week_html(html: str, q: str, kind: str, week_start_iso: str):
    """
    Разбираем «плоский» текст страницы недели.
    Формат блоков по дню:
      понедельник | 8 сентября
      Группа;Пара;Дисциплина, Вид;Преподаватель;№ ауд.;
      23ИСПп3-о9;2;...;Фамилия И.О.;СДО; ...
    """
    # <br> -> пробелы, затем тянем всё как текст
    html = re.sub(r"<br\s*/?>", " ", html, flags=re.I)
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)

    base = datetime.fromisoformat(week_start_iso).date()
    day_header_re = re.compile(
        r"^(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье)\s*\|\s*(\d{1,2})\s+[а-я]+",
        re.I
    )

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items, buf, cur_date = [], [], None

    def _flush():
        nonlocal buf, items, cur_date
        if not buf or not cur_date:
            buf = []; return
        seg = " ".join(buf)
        # вырезаем до заголовка колонок (если есть)
        p = seg.lower().find("группа;пара;дисциплина")
        if p != -1: seg = seg[p:]
        seg = re.sub(r"^группа;пара;дисциплина[^;]*;преподаватель;№ ауд.;\s*", "", seg, flags=re.I)
        toks = [t.strip() for t in seg.split(";") if t.strip()]

        needle = (q or "").lower()
        for i in range(0, len(toks) - 4, 5):
            group_field   = norm(toks[i])
            pair_field    = norm(toks[i+1])
            disc_type     = norm(toks[i+2])
            teacher_field = norm(toks[i+3])
            room_field    = norm(toks[i+4])

            if needle and needle not in f"{group_field} {teacher_field} {disc_type}".lower():
                continue

            # делим предмет/вид по последней запятой
            discipline, lesson_type = disc_type, None
            if "," in disc_type:
                left, right = disc_type.rsplit(",", 1)
                discipline = norm(left)
                lesson_type = norm(right)

            # дистанционно?
            is_remote = room_field.upper().startswith("СДО")

            # вычислим корпус по правилу из задания
            building = None
            if not is_remote:
                rm = (room_field or "").strip()
                if rm.isdigit():
                    n = int(rm)
                    building = "Колледж" if n < 100 else "Высшее Образование"
# КОД ДЛЯ CHAT-GPT: 11232131
            items.append({
                "date": cur_date.isoformat(),
                "order": int(pair_field) if pair_field.isdigit() else None,
                "time": None,  # время возьмём из локальных слотов при предпросмотре/импорте
                "discipline": discipline or None,
                "lesson_type": lesson_type or None,
                "teacher": teacher_field or None,
                "group": group_field or None,
                "room": None if is_remote else (room_field or None),
                "building": building,
                "is_remote": is_remote,
                "remote_platform": "СДО" if is_remote else None,
            })
        buf = []

    for ln in lines:
        m = day_header_re.match(ln)
        if m:
            _flush()
            day_idx = RU_DAY_TO_IDX[m.group(1).lower()]
            cur_date = base + timedelta(days=day_idx)
            continue
        if cur_date: buf.append(ln)
    _flush()

    items.sort(key=lambda x: (x["date"], x["order"] if x["order"] is not None else 99))
    return items

def fetch_week_from_ranepa(q: str, kind: str, sem: int, start: str, end: str):
    slug = _week_slug(start)  # ПН–СБ
    html = _get(f"{BASE}/{slug}")
    return _parse_week_html(html, q=q, kind=kind, week_start_iso=start)
