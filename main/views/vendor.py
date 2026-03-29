import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ..decorators import role_required
from ..forms import (
    PackageDayForm,
    PackageDayOptionForm,
    TravelPackageForm,
    TripItemAttachmentForm,
    TripItemVendorNotesForm,
    VendorBookingOperationsForm,
    VendorCancellationReviewForm,
)
from ..models import Booking, BookingOperation, PackageDayOption, TravelPackage, Trip, TripItem, TripItemAttachment
from ..notifications import create_notification
from ..services.access import _get_vendor_or_403, _sync_trip_status_from_booking
from ..services.cancellations import _calculate_refund_amount
from ..services.itineraries import (
    _build_booking_selection_items,
    _group_booking_selection_items,
    _sync_package_itinerary_json,
)
from ..services.trips import _build_trip_progress_summary, _build_trip_timeline_items


@login_required
@role_required(allowed_roles=['vendor'])
def vendor_dashboard(request):
    vendor = _get_vendor_or_403(request)
    vendor_bookings_qs = Booking.objects.filter(package__vendor=vendor)
    confirmed_bookings = vendor_bookings_qs.filter(status__in=['confirmed', 'trip_completed'])

    total_stats = confirmed_bookings.aggregate(
        total_revenue=Sum('total_price'),
        total_bookings=Count('id'),
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
            messages.error(request, 'Invalid status.')

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
        custom_itinerary__selections__selected_option__option_type='flight',
    ).select_related('user', 'package').distinct()

    return render(request, 'main/vendor/flight_bookings.html', {'bookings': bookings})


@login_required
@role_required(allowed_roles=['vendor'])
def vendor_package_list(request):
    vendor = _get_vendor_or_403(request)
    packages = TravelPackage.objects.filter(vendor=vendor).order_by('-created_at')
    return render(request, 'main/vendor/vendor_package_list.html', {'packages': packages})


@login_required
@role_required(allowed_roles=['vendor'])
def create_package(request):
    if request.method == 'POST':
        form = TravelPackageForm(request.POST, request.FILES)
        if form.is_valid():
            package = form.save(commit=False)
            package.vendor = _get_vendor_or_403(request)
            package.moderation_status = 'pending'
            package.moderation_notes = ''
            package.moderated_at = None
            package.save()
            messages.success(request, 'Package created and sent for admin review.')
            return redirect('vendor_dashboard')
    else:
        form = TravelPackageForm()
    return render(request, 'main/vendor/create_package.html', {
        'form': form,
        'page_title': 'Create New Travel Package',
        'submit_label': 'Create Package',
        'cancel_url': 'vendor_dashboard',
    })


@login_required
@role_required(allowed_roles=['vendor'])
def edit_package(request, package_id):
    vendor = _get_vendor_or_403(request)
    package = get_object_or_404(TravelPackage, pk=package_id, vendor=vendor)

    if request.method == 'POST':
        form = TravelPackageForm(request.POST, request.FILES, instance=package)
        if form.is_valid():
            package = form.save(commit=False)
            package.moderation_status = 'pending'
            package.moderation_notes = ''
            package.moderated_at = None
            package.save()
            messages.success(request, 'Package updated and sent for admin review.')
            return redirect('vendor_package_list')
    else:
        form = TravelPackageForm(instance=package)

    return render(request, 'main/vendor/create_package.html', {
        'form': form,
        'package': package,
        'page_title': 'Edit Travel Package',
        'submit_label': 'Save Changes',
        'cancel_url': 'vendor_package_list',
    })


@login_required
@role_required(allowed_roles=['vendor'])
def manage_itinerary(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)

    if package.vendor != _get_vendor_or_403(request):
        raise PermissionDenied
    package_days = package.package_days.prefetch_related('options').all()
    edit_day = None
    edit_option = None

    edit_day_id = request.GET.get('edit_day')
    if edit_day_id:
        edit_day = package_days.filter(pk=edit_day_id).first()

    edit_option_id = request.GET.get('edit_option')
    if edit_option_id:
        edit_option = PackageDayOption.objects.filter(
            package_day__package=package,
            pk=edit_option_id,
        ).select_related('package_day').first()

    day_form = PackageDayForm(instance=edit_day, package=package, prefix='day')
    option_form = PackageDayOptionForm(instance=edit_option, package=package, prefix='option')

    if request.method == 'POST':
        action = request.POST.get('action')
        day_id = request.POST.get('day_id') or None
        option_id = request.POST.get('option_id') or None

        if action == 'save_day':
            day_instance = package_days.filter(pk=day_id).first() if day_id else None
            day_form = PackageDayForm(request.POST, instance=day_instance, package=package, prefix='day')
            option_form = PackageDayOptionForm(package=package, prefix='option')
            if day_form.is_valid():
                day = day_form.save(commit=False)
                day.package = package
                day.save()
                _sync_package_itinerary_json(package)
                messages.success(request, 'Itinerary day saved successfully.')
                return redirect('manage_itinerary', package_id=package.id)
        elif action == 'save_option':
            option_instance = (
                PackageDayOption.objects.filter(package_day__package=package, pk=option_id).first()
                if option_id else None
            )
            option_form = PackageDayOptionForm(request.POST, instance=option_instance, package=package, prefix='option')
            day_form = PackageDayForm(package=package, prefix='day')
            if option_form.is_valid():
                option_form.save()
                _sync_package_itinerary_json(package)
                messages.success(request, 'Itinerary option saved successfully.')
                return redirect('manage_itinerary', package_id=package.id)
        elif action == 'delete_day':
            day_to_delete = package_days.filter(pk=day_id).first() if day_id else None
            if day_to_delete:
                day_to_delete.delete()
                _sync_package_itinerary_json(package)
                messages.success(request, 'Itinerary day deleted.')
                return redirect('manage_itinerary', package_id=package.id)
        elif action == 'delete_option':
            option_to_delete = (
                PackageDayOption.objects.filter(package_day__package=package, pk=option_id).first()
                if option_id else None
            )
            if option_to_delete:
                option_to_delete.delete()
                _sync_package_itinerary_json(package)
                messages.success(request, 'Itinerary option deleted.')
                return redirect('manage_itinerary', package_id=package.id)

    return render(request, 'main/vendor/manage_itinerary.html', {
        'package': package,
        'package_days': package_days,
        'day_form': day_form,
        'option_form': option_form,
        'editing_day': edit_day,
        'editing_option': edit_option,
    })


@login_required
@role_required(allowed_roles=['vendor'])
def vendor_trip_dashboard(request, trip_id):
    vendor = _get_vendor_or_403(request)
    trip = get_object_or_404(
        Trip.objects.select_related('booking', 'package', 'traveler', 'custom_itinerary', 'vendor')
        .prefetch_related('items__package_day', 'items__selected_option'),
        pk=trip_id,
        vendor=vendor,
    )

    return render(request, 'main/vendor/vendor_trip_dashboard.html', {
        'trip': trip,
        'booking': trip.booking,
        'package': trip.package,
        'traveler': trip.traveler,
        'timeline_items': _build_trip_timeline_items(trip),
        'progress_summary': _build_trip_progress_summary(trip),
    })


@login_required
@role_required(allowed_roles=['vendor'])
def update_trip_item_status(request, trip_item_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    vendor = _get_vendor_or_403(request)
    trip_item = get_object_or_404(
        TripItem.objects.select_related('trip', 'trip__vendor'),
        pk=trip_item_id,
    )

    if trip_item.trip.vendor_id != vendor.id:
        raise PermissionDenied

    new_status = request.POST.get('status', '').strip()
    allowed_statuses = {choice[0] for choice in TripItem.STATUS_CHOICES}

    if new_status not in allowed_statuses:
        messages.error(request, 'Invalid trip item status.')
        return redirect('vendor_trip_dashboard', trip_id=trip_item.trip_id)

    if trip_item.status != new_status:
        trip_item.status = new_status
        trip_item.save(update_fields=['status', 'updated_at'])
        create_notification(
            user=trip_item.trip.traveler,
            title='Trip item updated',
            message=f"Day {trip_item.day_number} for {trip_item.trip.package.name} is now {trip_item.get_status_display().lower()}.",
            notification_type='trip_update',
            target_url=reverse('trip_dashboard', args=[trip_item.trip_id]),
            related_trip=trip_item.trip,
        )
        messages.success(request, f'Trip item updated to {trip_item.get_status_display()}.')

    return redirect('vendor_trip_dashboard', trip_id=trip_item.trip_id)


@login_required
@role_required(allowed_roles=['vendor'])
def update_trip_item_notes(request, trip_item_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    vendor = _get_vendor_or_403(request)
    trip_item = get_object_or_404(
        TripItem.objects.select_related('trip', 'trip__vendor'),
        pk=trip_item_id,
    )

    if trip_item.trip.vendor_id != vendor.id:
        raise PermissionDenied

    form = TripItemVendorNotesForm(request.POST, instance=trip_item)
    if form.is_valid():
        form.save()
        messages.success(request, 'Trip item notes updated.')
    else:
        messages.error(request, 'Could not save trip item notes.')

    return redirect('vendor_trip_dashboard', trip_id=trip_item.trip_id)


@login_required
@role_required(allowed_roles=['vendor'])
def upload_trip_item_attachment(request, trip_item_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    vendor = _get_vendor_or_403(request)
    trip_item = get_object_or_404(
        TripItem.objects.select_related('trip', 'trip__vendor'),
        pk=trip_item_id,
    )

    if trip_item.trip.vendor_id != vendor.id:
        raise PermissionDenied

    form = TripItemAttachmentForm(
        request.POST,
        request.FILES,
        prefix=f'attachment-{trip_item.id}',
    )
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.trip_item = trip_item
        attachment.uploaded_by = request.user
        attachment.save()
        messages.success(request, 'Attachment uploaded successfully.')
    else:
        messages.error(request, 'Could not upload attachment. Please check the form fields.')

    return redirect('vendor_trip_dashboard', trip_id=trip_item.trip_id)


@login_required
@role_required(allowed_roles=['vendor'])
def delete_trip_item_attachment(request, attachment_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    vendor = _get_vendor_or_403(request)
    attachment = get_object_or_404(
        TripItemAttachment.objects.select_related('trip_item', 'trip_item__trip', 'trip_item__trip__vendor'),
        pk=attachment_id,
    )

    if attachment.trip_item.trip.vendor_id != vendor.id:
        raise PermissionDenied

    trip_id = attachment.trip_item.trip_id
    attachment.file.delete(save=False)
    attachment.delete()
    messages.success(request, 'Attachment deleted.')
    return redirect('vendor_trip_dashboard', trip_id=trip_id)


@login_required
@role_required(allowed_roles=['vendor'])
def export_booking_csv(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('user', 'package', 'custom_itinerary'),
        id=booking_id,
        package__vendor=_get_vendor_or_403(request),
    )

    from django.http import HttpResponse
    import csv

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename=\"booking_{booking.id}.csv\"'

    writer = csv.writer(response)
    writer.writerow(['User', 'Package', 'Option Type', 'Option', 'Price'])

    if booking.custom_itinerary:
        selections = booking.custom_itinerary.selections.select_related('package_day', 'selected_option')
        for sel in selections:
            writer.writerow([
                booking.user.username,
                booking.package.name,
                sel.selected_option.option_type,
                sel.selected_option.title,
                sel.selected_price,
            ])
    else:
        writer.writerow([
            booking.user.username,
            booking.package.name,
            'Default Package',
            'No customization',
            booking.total_price,
        ])

    return response
