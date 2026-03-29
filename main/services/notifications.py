from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import reverse

from ..models import CustomItinerary, TravelPackage
from ..notifications import create_notification
from .access import _get_vendor_or_403, _get_vendor_user


def _notify_custom_itinerary_saved(custom_itinerary):
    create_notification(
        user=custom_itinerary.user,
        title='Custom itinerary saved',
        message=f"Your custom itinerary for {custom_itinerary.package.name} was saved.",
        notification_type='custom_itinerary_saved',
        target_url=reverse('custom_itinerary_detail', args=[custom_itinerary.id]),
        related_custom_itinerary=custom_itinerary,
        dedupe_key=f"custom_itinerary_saved:{custom_itinerary.id}:{custom_itinerary.user_id}",
    )


def _notify_booking_confirmed(booking, *, is_custom):
    traveler_message = (
        f"Your custom booking for {booking.package.name} is confirmed."
        if is_custom else
        f"Your booking for {booking.package.name} is confirmed."
    )
    create_notification(
        user=booking.user,
        title='Payment successful',
        message=traveler_message,
        notification_type='payment_success',
        target_url=reverse('booking_confirmation', args=[booking.id]),
        related_booking=booking,
        related_trip=getattr(booking, 'trip', None),
        dedupe_key=f"payment_success:traveler:{booking.id}",
    )

    create_notification(
        user=_get_vendor_user(booking.package.vendor),
        title='New confirmed booking',
        message=f"{booking.user.username} confirmed a booking for {booking.package.name}.",
        notification_type='booking_created',
        target_url=reverse('vendor_bookings'),
        related_booking=booking,
        related_trip=getattr(booking, 'trip', None),
        dedupe_key=f"booking_created:vendor:{booking.id}",
    )


def _notify_payment_cancelled(request, detail_message):
    if not request.user.is_authenticated:
        return

    custom_itinerary_id = request.session.get('pending_custom_itinerary_id')
    package_id = request.session.get('pending_booking_package_id')
    sponsorship_package_id = request.session.get('pending_sponsorship_package_id')
    target_url = reverse('package_list')
    related_custom_itinerary = None
    dedupe_key = None

    if sponsorship_package_id:
        try:
            package = TravelPackage.objects.select_related('vendor').get(
                pk=sponsorship_package_id,
                vendor=_get_vendor_or_403(request),
            )
            target_url = reverse('vendor_package_list')
            dedupe_key = f"payment_cancelled:sponsorship:{package.id}:{request.user.id}"
        except (TravelPackage.DoesNotExist, PermissionDenied):
            package = None
    elif custom_itinerary_id:
        try:
            related_custom_itinerary = CustomItinerary.objects.select_related('package').get(
                pk=custom_itinerary_id,
                user=request.user,
            )
            target_url = reverse('custom_itinerary_detail', args=[related_custom_itinerary.id])
            dedupe_key = f"payment_cancelled:custom:{related_custom_itinerary.id}"
        except CustomItinerary.DoesNotExist:
            related_custom_itinerary = None
    elif package_id:
        target_url = reverse('package_detail', args=[package_id])
        dedupe_key = f"payment_cancelled:package:{package_id}:{request.user.id}"

    create_notification(
        user=request.user,
        title='Payment cancelled',
        message=detail_message,
        notification_type='payment_cancelled',
        target_url=target_url,
        related_custom_itinerary=related_custom_itinerary,
        dedupe_key=dedupe_key,
    )


def _notify_chat_message(message_obj):
    thread = message_obj.thread
    recipient = (
        _get_vendor_user(thread.vendor)
        if message_obj.sender_id == thread.traveler_id else
        thread.traveler
    )

    create_notification(
        user=recipient,
        title='New chat message',
        message=f"{message_obj.sender.username} sent you a new message about {thread.package.name if thread.package else 'your trip'}.",
        notification_type='chat_message',
        target_url=reverse('chat_thread_detail', args=[thread.id]),
        related_thread=thread,
    )

