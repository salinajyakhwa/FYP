from django.urls import path

from . import views


urlpatterns = [
    path('management/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('management/users/', views.manage_users, name='manage_users'),
    path('management/users/delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('management/vendors/', views.manage_vendors, name='manage_vendors'),
    path('management/vendor/<int:vendor_id>/update/<str:new_status>/', views.update_vendor_status, name='update_vendor_status'),
    path('management/cancellations/', views.manage_cancellation_requests, name='manage_cancellation_requests'),
    path('management/cancellations/<int:booking_id>/<str:decision>/', views.finalize_cancellation_request, name='finalize_cancellation_request'),
    path('management/payments/', views.manage_payment_logs, name='manage_payment_logs'),
    path('management/disputes/', views.manage_booking_disputes, name='manage_booking_disputes'),
    path('management/disputes/<int:dispute_id>/<str:new_status>/', views.update_booking_dispute, name='update_booking_dispute'),
    path('management/packages/', views.manage_package_moderation, name='manage_package_moderation'),
    path('management/packages/<int:package_id>/<str:new_status>/', views.update_package_moderation, name='update_package_moderation'),
]
