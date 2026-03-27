from django.urls import path, include
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.root_redirect_view, name='root_redirect'),
    path('tours/', views.package_list, name='package_list'),
    path('search/', views.search_results, name='search_results'),
    
    # 3. AUTH & DASHBOARD
    path('dashboard/', views.dashboard, name='dashboard'),
    path('register/', views.register, name='register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('check-email/', views.check_email, name='check_email'), # New URL
    path('activate/<uidb64>/<token>/', views.verify_email, name='verify_email'), # New URL
    path('login/', auth_views.LoginView.as_view(template_name='main/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # 4. PACKAGE DETAILS & BOOKING
    path('package/<int:package_id>/', views.package_detail, name='package_detail'),
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

    # 5. VENDOR
    path('vendor/dashboard/', views.vendor_dashboard, name='vendor_dashboard'),
    path('vendor/bookings/', views.vendor_bookings, name='vendor_bookings'),
    path('vendor/trip/<int:trip_id>/', views.vendor_trip_dashboard, name='vendor_trip_dashboard'),
    path('vendor/trip-item/<int:trip_item_id>/status/', views.update_trip_item_status, name='update_trip_item_status'),
    path('vendor/trip-item/<int:trip_item_id>/notes/', views.update_trip_item_notes, name='update_trip_item_notes'),
    path('vendor/trip-item/<int:trip_item_id>/attachments/upload/', views.upload_trip_item_attachment, name='upload_trip_item_attachment'),
    path('vendor/trip-item-attachment/<int:attachment_id>/delete/', views.delete_trip_item_attachment, name='delete_trip_item_attachment'),
    path('vendor/booking/<int:booking_id>/update/<str:new_status>/', views.update_booking_status, name='update_booking_status'),
    path('vendor/packages/', views.vendor_package_list, name='vendor_package_list'),
    path('vendor/package/create/', views.create_package, name='create_package'),
    path('vendor/package/<int:package_id>/manage-itinerary/', views.manage_itinerary, name='manage_itinerary'),

    # 5.1 MANAGEMENT
    path('management/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('management/users/', views.manage_users, name='manage_users'),
    path('management/users/delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('management/vendors/', views.manage_vendors, name='manage_vendors'),
    path('management/vendor/<int:vendor_id>/update/<str:new_status>/', views.update_vendor_status, name='update_vendor_status'),

    # 6. EXTRAS
    path('about/', views.about, name='about'),
    path('compare/', views.compare_packages, name='compare_packages'),
    path('profile/', views.profile, name='profile'),

    # 7. PASSWORDS
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='main/password_reset.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='main/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='main/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='main/password_reset_complete.html'), name='password_reset_complete'),

    # 8 PAYMENT
    path('payment/choose/<int:package_id>/', views.choose_payment, name='choose_payment'),
    path('payment/choose/custom-itinerary/<int:custom_itinerary_id>/', views.choose_custom_itinerary_payment, name='choose_custom_itinerary_payment'),
    path('create-checkout-session/<int:package_id>/', views.create_checkout_session, name='create_checkout_session'),
    path('create-checkout-session/custom-itinerary/<int:custom_itinerary_id>/', views.create_custom_itinerary_checkout_session, name='create_custom_itinerary_checkout_session'),
    path('payment/esewa-checkout/<int:package_id>/', views.esewa_checkout, name='esewa_checkout'),
    path('payment/esewa-checkout/custom-itinerary/<int:custom_itinerary_id>/', views.esewa_custom_itinerary_checkout, name='esewa_custom_itinerary_checkout'),
    path('payment/esewa-verify/', views.esewa_verify, name='esewa_verify'),
    path('payment-success/', views.payment_success, name= 'payment_success'),
    path('payment-cancelled/', views.payment_cancelled, name='payment_cancelled'),

    path('booking/confirmation/<int:booking_id>/', views.booking_confirmation, name='booking_confirmation'),
    path('vendor/booking/<int:booking_id>/csv/', views.export_booking_csv, name='export_booking_csv'),
    path('vendor/flights/', views.flight_bookings, name='flight_bookings'),
    path('accounts/', include('allauth.urls')),
]
