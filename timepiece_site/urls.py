from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

from catalog import views as catalog_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # logout — должен идти до include("django.contrib.auth.urls")
    path("accounts/logout/", catalog_views.logout_view, name="logout"),

    # регистрация + стандартные login/password/reset от Django
    path("accounts/signup/", catalog_views.signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),

    # webhook от Telegram
    path("telegram/webhook/", catalog_views.telegram_webhook, name="telegram_webhook"),

    # сайт
    path("", include("catalog.urls")),
]

# ✅ MEDIA раздаём всегда (в продакшене тоже), чтобы картинки из админки работали на Render
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
