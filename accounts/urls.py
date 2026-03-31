from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views


urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('register/', views.register, name='register'),
    path('register/vendor/', views.vendor_register, name='vendor_register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('verify-otp/resend/', views.resend_otp, name='resend_otp'),
    path('check-email/', views.check_email, name='check_email'),
    path('activate/<uidb64>/<token>/', views.verify_email, name='verify_email'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('reactivate-account/', views.reactivate_account, name='reactivate_account'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('profile/', views.profile, name='profile'),
    path(
        'password_reset/',
        auth_views.PasswordResetView.as_view(template_name='main/password_reset.html'),
        name='password_reset',
    ),
    path(
        'password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(template_name='main/password_reset_done.html'),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(template_name='main/password_reset_confirm.html'),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(template_name='main/password_reset_complete.html'),
        name='password_reset_complete',
    ),
    path('accounts/', include('allauth.urls')),
]
