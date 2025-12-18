from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from catalog import views as catalog_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # наша собственная вьюха logout — должна идти до include("django.contrib.auth.urls")
    path("accounts/logout/", catalog_views.logout_view, name="logout"),

    # регистрация + стандартные login/password/reset от Django
    path("accounts/signup/", catalog_views.signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("telegram/webhook/", catalog_views.telegram_webhook, name="telegram_webhook"),
    path("", include("catalog.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)