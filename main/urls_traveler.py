from django.urls import path

from . import views


urlpatterns = [
    path('package/<int:package_id>/', views.package_detail, name='package_detail'),
    path('package/<int:package_id>/start-booking/', views.start_package_booking, name='start_package_booking'),
    path('custom-itinerary/<int:custom_itinerary_id>/', views.custom_itinerary_detail, name='custom_itinerary_detail'),
    path('chat/', views.chat_thread_list, name='chat_thread_list'),
    path('chat/open/package/<int:package_id>/', views.chat_thread_open, name='chat_thread_open'),
    path('chat/thread/<int:thread_id>/', views.chat_thread_detail, name='chat_thread_detail'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:notification_id>/open/', views.mark_notification_read_view, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('trip/<int:trip_id>/', views.trip_dashboard, name='trip_dashboard'),
    path('package/<int:package_id>/add_review/', views.add_review, name='add_review'),
    path('booking/cancel/<int:booking_id>/', views.cancel_booking, name='cancel_booking'),
    path('booking/dispute/<int:booking_id>/', views.submit_booking_dispute, name='submit_booking_dispute'),
    path('booking/confirmation/<int:booking_id>/', views.booking_confirmation, name='booking_confirmation'),
]
