from django.urls import path

from . import views


urlpatterns = [
    path('vendor/dashboard/', views.vendor_dashboard, name='vendor_dashboard'),
    path('vendor/bookings/', views.vendor_bookings, name='vendor_bookings'),
    path('vendor/trip/<int:trip_id>/', views.vendor_trip_dashboard, name='vendor_trip_dashboard'),
    path('vendor/trip-item/<int:trip_item_id>/status/', views.update_trip_item_status, name='update_trip_item_status'),
    path('vendor/trip-item/<int:trip_item_id>/notes/', views.update_trip_item_notes, name='update_trip_item_notes'),
    path('vendor/trip-item/<int:trip_item_id>/attachments/upload/', views.upload_trip_item_attachment, name='upload_trip_item_attachment'),
    path('vendor/trip-item-attachment/<int:attachment_id>/delete/', views.delete_trip_item_attachment, name='delete_trip_item_attachment'),
    path('vendor/booking/<int:booking_id>/update/<str:new_status>/', views.update_booking_status, name='update_booking_status'),
    path('vendor/booking/<int:booking_id>/operations/', views.update_booking_operations, name='update_booking_operations'),
    path('vendor/booking/<int:booking_id>/cancellation-review/', views.review_cancellation_request, name='review_cancellation_request'),
    path('vendor/booking/<int:booking_id>/csv/', views.export_booking_csv, name='export_booking_csv'),
    path('vendor/flights/', views.flight_bookings, name='flight_bookings'),
    path('vendor/packages/', views.vendor_package_list, name='vendor_package_list'),
    path('vendor/package/create/', views.create_package, name='create_package'),
    path('vendor/package/<int:package_id>/edit/', views.edit_package, name='edit_package'),
    path('vendor/package/<int:package_id>/manage-itinerary/', views.manage_itinerary, name='manage_itinerary'),
    path('vendor/package/<int:package_id>/sponsorship/', views.choose_sponsorship_payment, name='choose_sponsorship_payment'),
    path('vendor/capacity-request/<int:request_id>/<str:decision>/', views.review_capacity_request, name='review_capacity_request'),
]
