# api/services/ranepa_headless.py
from playwright.sync_api import sync_playwright
from datetime import datetime

BASE = "https://zf-ranepa-rasp.ru"
MONTH_SLUGS_RU = {1:"jan",2:"feb",3:"mar",4:"apr",5:"may",6:"jun",7:"jul",8:"aug",9:"sep",10:"oct",11:"nov",12:"dec"}

def fetch_week_headless(q: str, sem: int, start: str, end: str):
    mon = MONTH_SLUGS_RU[datetime.fromisoformat(start).month]
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        page = br.new_page()
        page.goto(f"{BASE}/{mon}", wait_until="domcontentloaded")
        # TODO: клик по нужной неделе, ввод q в поле поиска, дождаться отрисовки
        # Ниже селекторы-заглушки — посмотри имена инпутов в браузере и поправь:
        # page.click("text='9 сентября - 14 сентября'")
        # page.fill("input[placeholder*='группа'], input[placeholder*='преподав']", q)
        # page.wait_for_timeout(1000)
        # Забор DOM и разбор:
        html = page.content()
        br.close()
    from .services.ranepa import _parse_week_html
    return _parse_week_html(html, q=q, kind="group")