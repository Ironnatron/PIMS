from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from inventory.views import health

urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/password/", auth_views.PasswordChangeView.as_view(
        template_name="registration/password_change.html",
        success_url="/accounts/password/done/",
    ), name="password_change"),
    path("accounts/password/done/", auth_views.PasswordChangeDoneView.as_view(
        template_name="registration/password_change_done.html",
    ), name="password_change_done"),
    path("", include("inventory.urls")),
]
