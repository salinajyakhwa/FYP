from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import BookingCancellationRequestForm, BookingDisputeForm, ReviewForm
from .models import Booking, Review, TravelPackage
from .services.access import _get_vendor_or_403
from .services.itineraries import _build_booking_selection_items, _group_booking_selection_items


@login_required
def my_bookings(request):
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related('package', 'package__vendor', 'custom_itinerary', 'trip', 'operations')
        .prefetch_related(
            'custom_itinerary__selections__package_day',
            'custom_itinerary__selections__selected_option',
        )
        .order_by('-booking_date')
    )
    for booking in bookings:
        booking.selection_items = _build_booking_selection_items(booking.custom_itinerary)
        booking.selection_groups = _group_booking_selection_items(booking.selection_items)
        booking.operation_record = getattr(booking, 'operations', None)
    return render(request, 'main/traveler/my_bookings.html', {'bookings': bookings})


@login_required
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)

    if booking.user != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        if booking.status in ['pending', 'confirmed']:
            form = BookingCancellationRequestForm(request.POST, instance=booking)
            if form.is_valid():
                booking = form.save(commit=False)
                booking.status = 'cancellation_requested'
                booking.cancellation_requested_at = timezone.now()
                booking.save(update_fields=['cancellation_reason', 'status', 'cancellation_requested_at'])
                messages.success(request, 'Cancellation request sent to the vendor for review.')
            else:
                messages.error(request, 'Please add a short cancellation reason.')
        else:
            messages.error(request, 'This booking cannot be cancelled.')

    return redirect('my_bookings')


@login_required
def add_review(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)

    if Review.objects.filter(user=request.user, package=package).exists():
        messages.error(request, 'You have already submitted a review for this package.')
        return redirect('package_detail', package_id=package.id)

    can_review = Booking.objects.filter(
        user=request.user,
        package=package,
        status='confirmed',
        package__end_date__lt=timezone.now().date()
    ).exists()

    if not can_review:
        messages.error(request, 'You can only review packages after you have completed the trip.')
        return redirect('package_detail', package_id=package.id)

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.package = package
            review.user = request.user
            review.is_verified = True
            review.save()
            messages.success(request, 'Thank you for your review!')
            return redirect('package_detail', package_id=package.id)

    return redirect('package_detail', package_id=package.id)


@login_required
def submit_booking_dispute(request, booking_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    form = BookingDisputeForm(request.POST)

    if form.is_valid():
        dispute = form.save(commit=False)
        dispute.booking = booking
        dispute.opened_by = request.user
        dispute.save()
        messages.success(request, 'Dispute submitted for admin review.')
    else:
        messages.error(request, 'Please fill in both the dispute title and details.')

    return redirect('my_bookings')


@login_required
def booking_confirmation(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('package', 'package__vendor', 'custom_itinerary', 'operations').prefetch_related(
            'custom_itinerary__selections__package_day',
            'custom_itinerary__selections__selected_option',
        ),
        pk=booking_id,
    )

    if booking.user != request.user:
        raise PermissionDenied

    selection_items = _build_booking_selection_items(booking.custom_itinerary)
    return render(request, 'main/traveler/booking_confirmation.html', {
        'booking': booking,
        'package': booking.package,
        'selection_items': selection_items,
        'selection_groups': _group_booking_selection_items(selection_items),
        'operation_record': getattr(booking, 'operations', None),
    })


@login_required
def export_booking_csv(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('user', 'package', 'custom_itinerary'),
        id=booking_id,
        package__vendor=_get_vendor_or_403(request)
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="booking_{booking.id}.csv"'

    import csv
    writer = csv.writer(response)
    writer.writerow(['User', 'Package', 'Option Type', 'Option', 'Price'])

    if booking.custom_itinerary:
        selections = booking.custom_itinerary.selections.select_related(
            'package_day', 'selected_option'
        )

        for sel in selections:
            writer.writerow([
                booking.user.username,
                booking.package.name,
                sel.selected_option.option_type,
                sel.selected_option.title,
                sel.selected_price
            ])
    else:
        writer.writerow([
            booking.user.username,
            booking.package.name,
            'Default Package',
            'No customization',
            booking.total_price
        ])

    return response
