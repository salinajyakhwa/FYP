from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.package_list, name='package_list'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('about/', views.about, name='about'),
    path('package/<int:package_id>/', views.package_detail, name='package_detail'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='main/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('book/<int:package_id>/', views.book_package, name='book_package'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('package/<int:package_id>/add_review/', views.add_review, name='add_review'),
    path('vendor/dashboard/', views.vendor_dashboard, name='vendor_dashboard'),
    path('vendor/package/create/', views.create_package, name='create_package'),
    path('vendor/package/<int:package_id>/manage-itinerary/', views.manage_itinerary, name='manage_itinerary'),
    path('compare/', views.compare_packages, name='compare_packages'),
    path('profile/', views.profile, name='profile'),
    path('booking/cancel/<int:booking_id>/', views.cancel_booking, name='cancel_booking'),

    # Password Reset URLs
    path('password_reset/', 
         auth_views.PasswordResetView.as_view(template_name='main/password_reset.html'), 
         name='password_reset'),
    path('password_reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='main/password_reset_done.html'), 
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='main/password_reset_confirm.html'), 
         name='password_reset_confirm'),
    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='main/password_reset_complete.html'), 
         name='password_reset_complete'),
]
