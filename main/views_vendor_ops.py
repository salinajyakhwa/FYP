import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth

from .decorators import role_required
from .forms import VendorBookingOperationsForm, VendorCancellationReviewForm
from .models import Booking, BookingOperation, BookingDispute, TravelPackage, Trip
from .services.access import _get_vendor_or_403, _sync_trip_status_from_booking
from .services.cancellations import _calculate_refund_amount
from .services.itineraries import _build_booking_selection_items, _group_booking_selection_items
from .services.vendor_ops import send_vendor_status_email


@login_required
@role_required(allowed_roles=['vendor'])
def vendor_dashboard(request):
    vendor = _get_vendor_or_403(request)
    vendor_bookings_qs = Booking.objects.filter(package__vendor=vendor)
    confirmed_bookings = vendor_bookings_qs.filter(status__in=['confirmed', 'trip_completed'])

    total_stats = confirmed_bookings.aggregate(
        total_revenue=Sum('total_price'),
        total_bookings=Count('id')
    )
    total_revenue = total_stats.get('total_revenue') or 0
    total_bookings_count = total_stats.get('total_bookings') or 0

    twelve_months_ago = timezone.now() - timezone.timedelta(days=365)
    monthly_revenue_data = confirmed_bookings.filter(
        booking_date__gte=twelve_months_ago
    ).annotate(
        month=TruncMonth('booking_date')
    ).values('month').annotate(
        revenue=Sum('total_price')
    ).order_by('month')

    monthly_labels = [item['month'].strftime('%b %Y') for item in monthly_revenue_data]
    monthly_values = [float(item['revenue']) for item in monthly_revenue_data]

    package_booking_data = confirmed_bookings.values('package__name').annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    package_labels = [item['package__name'] for item in package_booking_data]
    package_values = [item['count'] for item in package_booking_data]

    recent_bookings = vendor_bookings_qs.order_by('-booking_date')[:1]

    dashboard_queue = {
        'pending_bookings': vendor_bookings_qs.filter(status='pending').count(),
        'in_review_bookings': vendor_bookings_qs.filter(status='in_review').count(),
        'refund_requests': vendor_bookings_qs.filter(status__in=['cancellation_requested', 'cancellation_reviewed']).count(),
        'active_trips': Trip.objects.filter(vendor=vendor).exclude(status__in=['completed', 'cancelled', 'no_show']).count(),
    }

    return render(request, 'main/vendor/vendor_dashboard.html', {
        'total_revenue': total_revenue,
        'total_bookings_count': total_bookings_count,
        'monthly_revenue_labels': json.dumps(monthly_labels),
        'monthly_revenue_values': json.dumps(monthly_values),
        'package_booking_labels': json.dumps(package_labels),
        'package_booking_values': json.dumps(package_values),
        'dashboard_queue': dashboard_queue,
        'recent_bookings': recent_bookings,
    })


@login_required
@role_required(allowed_roles=['vendor'])
def vendor_bookings(request):
    vendor = _get_vendor_or_403(request)

    bookings = Booking.objects.filter(package__vendor=vendor)\
        .select_related('user', 'package', 'custom_itinerary', 'trip', 'operations')\
        .prefetch_related(
            'custom_itinerary__selections__package_day',
            'custom_itinerary__selections__selected_option'
        )\
        .order_by('-booking_date')

    for booking in bookings:
        booking.selection_items = _build_booking_selection_items(booking.custom_itinerary)
        booking.selection_groups = _group_booking_selection_items(booking.selection_items)
        booking.operation_record = getattr(booking, 'operations', None)
        if booking.status == 'cancellation_requested':
            booking.cancellation_review_form = VendorCancellationReviewForm(
                instance=booking,
                booking=booking,
                prefix=f'cancel-{booking.id}',
            )
        booking.operation_form = VendorBookingOperationsForm(
            instance=booking.operation_record,
            prefix=f'ops-{booking.id}',
        )

    return render(request, 'main/vendor/vendor_bookings.html', {'bookings': bookings})


@login_required
@role_required(allowed_roles=['vendor'])
def update_booking_status(request, booking_id, new_status):
    vendor = _get_vendor_or_403(request)
    booking = get_object_or_404(Booking, id=booking_id, package__vendor=vendor)

    if request.method == 'POST':
        if new_status in ['confirmed', 'in_review', 'trip_completed', 'no_show', 'cancelled']:
            booking.status = new_status
            booking.save(update_fields=['status'])
            _sync_trip_status_from_booking(booking)
            messages.success(request, f"Booking status updated to {booking.get_status_display()}.")
        else:
            messages.error(request, "Invalid status.")

    return redirect('vendor_bookings')


@login_required
@role_required(allowed_roles=['vendor'])
def update_booking_operations(request, booking_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    vendor = _get_vendor_or_403(request)
    booking = get_object_or_404(Booking, id=booking_id, package__vendor=vendor)
    operations, _ = BookingOperation.objects.get_or_create(booking=booking)
    form = VendorBookingOperationsForm(request.POST, request.FILES, instance=operations, prefix=f'ops-{booking.id}')

    if form.is_valid():
        form.save()
        if booking.status == 'confirmed':
            booking.status = 'in_review'
            booking.save(update_fields=['status'])
            _sync_trip_status_from_booking(booking)
        messages.success(request, 'Booking operations updated.')
    else:
        messages.error(request, 'Please correct the booking operations form.')

    return redirect('vendor_bookings')


@login_required
@role_required(allowed_roles=['vendor'])
def review_cancellation_request(request, booking_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    vendor = _get_vendor_or_403(request)
    booking = get_object_or_404(Booking, id=booking_id, package__vendor=vendor)

    if booking.status != 'cancellation_requested':
        messages.error(request, 'This booking is not waiting for cancellation review.')
        return redirect('vendor_bookings')

    form = VendorCancellationReviewForm(
        request.POST,
        instance=booking,
        booking=booking,
        prefix=f'cancel-{booking.id}',
    )
    if not form.is_valid():
        messages.error(request, 'Please correct the cancellation review form.')
        return redirect('vendor_bookings')

    booking = form.save(commit=False)
    booking.refund_amount = _calculate_refund_amount(booking.total_price, booking.vendor_committed_cost)
    booking.status = 'cancellation_reviewed'
    booking.cancellation_reviewed_at = timezone.now()
    booking.save(update_fields=[
        'vendor_committed_cost',
        'vendor_cancellation_notes',
        'refund_amount',
        'status',
        'cancellation_reviewed_at',
    ])

    messages.success(request, 'Cancellation review sent for admin approval.')
    return redirect('vendor_bookings')


@login_required
@role_required(allowed_roles=['vendor'])
def flight_bookings(request):
    vendor = _get_vendor_or_403(request)

    bookings = Booking.objects.filter(
        package__vendor=vendor,
        custom_itinerary__selections__selected_option__option_type='flight'
    ).select_related('user', 'package').distinct()

    return render(request, 'main/vendor/flight_bookings.html', {'bookings': bookings})
