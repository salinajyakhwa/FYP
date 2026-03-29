from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from ..models import ChatThread


def _safe_int(value, default, minimum=0):
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def _sync_trip_status_from_booking(booking):
    trip = getattr(booking, 'trip', None)
    if not trip:
        return

    status_map = {
        'confirmed': 'ready',
        'in_review': 'ready',
        'trip_completed': 'completed',
        'no_show': 'no_show',
        'cancelled': 'cancelled',
        'refund_processed': 'cancelled',
        'partially_refunded': 'cancelled',
    }
    trip_status = status_map.get(booking.status)
    if trip_status and trip.status != trip_status:
        trip.status = trip_status
        trip.save(update_fields=['status', 'updated_at'])


def _get_vendor_or_403(request):
    try:
        return request.user.userprofile.vendor
    except Exception:
        raise PermissionDenied


def _get_vendor_user(vendor):
    return vendor.user_profile.user


def _get_chat_thread_for_user_or_403(user, thread_id):
    thread = get_object_or_404(
        ChatThread.objects.select_related(
            'traveler',
            'vendor',
            'vendor__user_profile',
            'vendor__user_profile__user',
            'package',
        ).prefetch_related('messages__sender'),
        pk=thread_id,
        is_active=True,
    )

    is_traveler = thread.traveler_id == user.id
    is_vendor = _get_vendor_user(thread.vendor).id == user.id
    if not (is_traveler or is_vendor):
        raise PermissionDenied

    return thread

