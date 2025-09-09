from django.conf import settings
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.shortcuts import resolve_url

EXEMPT_PREFIXES = ("/admin/", "/static/", "/media/")

def _get_cfg():
    cfg = cache.get("site_cfg")
    if cfg is None:
        from .models import SiteConfig
        cfg = SiteConfig.objects.first()
        cache.set("site_cfg", cfg, 10)  # лёгкий кэш на 10с
    return cfg

class MaintenanceModeMiddleware(MiddlewareMixin):
    """
    - Если maintenance_enabled + maintenance_hard: показываем 503 заглушку всем,
      КРОМЕ /admin/ и LOGIN_URL, а также staff/superuser.
    - Иначе пропускаем; мягкий баннер рисуется через контекст-процессор (ниже).
    """

    def process_request(self, request):
        path = request.path or "/"

        # исключения по путям
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return None

        # исключение для страницы логина
        try:
            login_path = resolve_url(getattr(settings, "LOGIN_URL", "/accounts/login/"))
        except Exception:
            login_path = "/accounts/login/"
        if path.startswith(login_path):
            return None

        cfg = _get_cfg()
        if not cfg or not cfg.maintenance_enabled:
            return None

        # жёсткая заглушка 503 — пускаем админов/персонал внутрь, остальным maintenance.html
        if cfg.maintenance_hard and not (request.user.is_authenticated and request.user.is_staff):
            return render(request, "maintenance.html", {"message": cfg.message}, status=503)

        return None
