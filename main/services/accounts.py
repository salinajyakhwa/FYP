from django.contrib.auth.models import User
from django.utils import timezone

from ..models import Booking, BookingDispute, TravelPackage, Trip


def anonymize_user_account(user):
    user.username = f"deleted_user_{user.id}"
    user.email = f"deleted_user_{user.id}@deleted.local"
    user.first_name = ''
    user.last_name = ''
    user.is_active = False
    user.set_unusable_password()
    user.save(update_fields=['username', 'email', 'first_name', 'last_name', 'is_active', 'password'])

    profile = getattr(user, 'userprofile', None)
    if profile:
        profile.bio = ''
        profile.account_deleted_at = timezone.now()
        profile.save(update_fields=['bio', 'account_deleted_at'])


def get_vendor_deletion_blockers(vendor):
    active_package_count = TravelPackage.objects.filter(
        vendor=vendor,
        moderation_status__in=['approved', 'pending'],
    ).count()
    pending_booking_count = Booking.objects.filter(
        package__vendor=vendor,
        status__in=['pending', 'confirmed', 'in_review', 'cancellation_requested', 'cancellation_reviewed'],
    ).count()
    active_trip_count = Trip.objects.filter(
        vendor=vendor,
        status__in=['planned', 'ready', 'in_progress'],
    ).count()
    open_dispute_count = BookingDispute.objects.filter(
        booking__package__vendor=vendor,
        status__in=['open', 'reviewing'],
    ).count()
    refund_in_progress_count = Booking.objects.filter(
        package__vendor=vendor,
        status__in=['cancellation_requested', 'cancellation_reviewed'],
    ).count()

    return {
        'active_packages': active_package_count,
        'pending_bookings': pending_booking_count,
        'active_trips': active_trip_count,
        'open_disputes': open_dispute_count,
        'refunds_in_progress': refund_in_progress_count,
    }


def vendor_can_be_deactivated(vendor):
    blockers = get_vendor_deletion_blockers(vendor)
    return not any(blockers.values()), blockers
