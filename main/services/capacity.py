from django.db.models import Sum
from django.utils import timezone

from ..models import Booking, BookingCapacityRequest


CAPACITY_BOOKING_STATUSES = ['confirmed', 'in_review', 'trip_completed']


def get_package_capacity_summary(package):
    booked_travelers = (
        Booking.objects.filter(package=package, status__in=CAPACITY_BOOKING_STATUSES)
        .aggregate(total=Sum('number_of_travelers'))
        .get('total')
        or 0
    )
    remaining_capacity = max(package.max_travelers - booked_travelers, 0)
    return {
        'max_travelers': package.max_travelers,
        'booked_travelers': booked_travelers,
        'remaining_capacity': remaining_capacity,
    }


def get_matching_approved_capacity_request(*, traveler, package, adult_count, child_count):
    return (
        BookingCapacityRequest.objects.filter(
            traveler=traveler,
            package=package,
            adult_count=adult_count,
            child_count=child_count,
            status='approved',
            approved_payment_used_at__isnull=True,
        )
        .order_by('-reviewed_at', '-created_at')
        .first()
    )


def can_proceed_with_capacity(*, traveler, package, adult_count, child_count):
    requested_total = adult_count + child_count
    summary = get_package_capacity_summary(package)
    if requested_total <= summary['remaining_capacity']:
        return True, None, summary

    approved_request = get_matching_approved_capacity_request(
        traveler=traveler,
        package=package,
        adult_count=adult_count,
        child_count=child_count,
    )
    return approved_request is not None, approved_request, summary


def mark_capacity_request_used(capacity_request):
    if not capacity_request or capacity_request.status != 'approved':
        return

    capacity_request.status = 'converted'
    capacity_request.approved_payment_used_at = timezone.now()
    capacity_request.save(update_fields=['status', 'approved_payment_used_at', 'updated_at'])
