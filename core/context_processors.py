from django.conf import settings
from django.shortcuts import resolve_url
from .middleware import _get_cfg, EXEMPT_PREFIXES

def site_flags(request):
    """
    Даёт шаблонам флаги для мягкого баннера техработ.
    Баннер НЕ показываем на /admin/* и на LOGIN_URL.
    """
    path = (getattr(request, "path", "/") or "/")
    if any(path.startswith(p) for p in EXEMPT_PREFIXES):
        return {"MAINTENANCE_SOFT": False, "MAINTENANCE_MESSAGE": ""}

    try:
        login_path = resolve_url(getattr(settings, "LOGIN_URL", "/accounts/login/"))
    except Exception:
        login_path = "/accounts/login/"
    if path.startswith(login_path):
        return {"MAINTENANCE_SOFT": False, "MAINTENANCE_MESSAGE": ""}

    cfg = _get_cfg()
    soft = bool(cfg and cfg.maintenance_enabled and not cfg.maintenance_hard)
    return {
        "MAINTENANCE_SOFT": soft,
        "MAINTENANCE_MESSAGE": (cfg.message if (cfg and soft) else "")
    }
