"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required, user_passes_test
from api import views as api_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.groups.filter(name="Admin").exists())

@ensure_csrf_cookie
def index(request):
    return render(request, "index.html")

@login_required
@ensure_csrf_cookie
def teacher_page(request):
    return render(request, "teacher.html")

@login_required
@user_passes_test(is_admin)
@ensure_csrf_cookie
def admin_generator_page(request):
    return render(request, "admin_generator.html")

@login_required
@user_passes_test(is_admin)
@ensure_csrf_cookie
def admin_overview_page(request):
    return render(request, "admin_overview.html")

@login_required
@user_passes_test(is_admin)
@ensure_csrf_cookie
def admin_studio_page(request):
    return render(request, "admin_studio.html")

@login_required
@user_passes_test(is_admin)
@ensure_csrf_cookie
def admin_integrations_page(request):
    return render(request, "admin_integrations.html")

urlpatterns = [
    path("", index, name="index"),
    re_path(r"^admin/generator/?$", admin_generator_page, name="admin_generator"),
    re_path(r"^admin/overview/?$",  admin_overview_page,  name="admin_overview"),
    re_path(r"^admin/studio/?$",    admin_studio_page,    name="admin_studio"),
    re_path(r"^admin/integrations/?$", admin_integrations_page, name="admin_integrations"),
    path("admin/conflicts/", TemplateView.as_view(template_name="admin_conflicts.html"), name="admin_conflicts"),

    # алиасы на случай конфликтов/отладки (необязательно)
    path("generator/", admin_generator_page),
    path("overview/",  admin_overview_page),
    path("studio/",    admin_studio_page),
    path("integrations/",    admin_integrations_page),

    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="index"), name="logout"),
    path("teacher/", teacher_page, name="teacher"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)