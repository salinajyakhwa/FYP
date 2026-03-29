from django.urls import path

from . import views


urlpatterns = [
    path('payment/choose/<int:package_id>/', views.choose_payment, name='choose_payment'),
    path('payment/choose/custom-itinerary/<int:custom_itinerary_id>/', views.choose_custom_itinerary_payment, name='choose_custom_itinerary_payment'),
    path('payment/choose/sponsorship/<int:package_id>/', views.choose_sponsorship_payment, name='choose_sponsorship_payment_alias'),
    path('create-checkout-session/<int:package_id>/', views.create_checkout_session, name='create_checkout_session'),
    path('create-checkout-session/custom-itinerary/<int:custom_itinerary_id>/', views.create_custom_itinerary_checkout_session, name='create_custom_itinerary_checkout_session'),
    path('create-checkout-session/sponsorship/<int:package_id>/', views.create_sponsorship_checkout_session, name='create_sponsorship_checkout_session'),
    path('payment/esewa-checkout/<int:package_id>/', views.esewa_checkout, name='esewa_checkout'),
    path('payment/esewa-checkout/custom-itinerary/<int:custom_itinerary_id>/', views.esewa_custom_itinerary_checkout, name='esewa_custom_itinerary_checkout'),
    path('payment/esewa-checkout/sponsorship/<int:package_id>/', views.esewa_sponsorship_checkout, name='esewa_sponsorship_checkout'),
    path('payment/esewa-verify/', views.esewa_verify, name='esewa_verify'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('payment-cancelled/', views.payment_cancelled, name='payment_cancelled'),
]
