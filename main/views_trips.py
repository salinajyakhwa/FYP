from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .decorators import role_required
from .forms import TripItemAttachmentForm, TripItemVendorNotesForm
from .models import Trip, TripItem, TripItemAttachment
from .notifications import create_notification
from .services.access import _get_vendor_or_403
from .services.trips import (
    _build_trip_next_action,
    _build_trip_progress_summary,
    _build_trip_recent_attachments,
    _build_trip_timeline_items,
    _build_trip_timeline_sections,
)


@login_required
def trip_dashboard(request, trip_id):
    trip = get_object_or_404(
        Trip.objects.select_related('booking', 'package', 'vendor', 'custom_itinerary')
        .prefetch_related('items__package_day', 'items__selected_option'),
        pk=trip_id,
    )

    if trip.traveler_id != request.user.id:
        raise PermissionDenied

    timeline_items = _build_trip_timeline_items(trip)
    progress_summary = _build_trip_progress_summary(trip)
    recent_attachments = _build_trip_recent_attachments(timeline_items)
    next_action = _build_trip_next_action(timeline_items)
    timeline_section_data = _build_trip_timeline_sections(trip, timeline_items)

    return render(request, 'main/traveler/trip_dashboard.html', {
        'trip': trip,
        'booking': trip.booking,
        'package': trip.package,
        'timeline_items': timeline_items,
        'timeline_sections': timeline_section_data['sections'],
        'current_day_number': timeline_section_data['current_day_number'],
        'progress_summary': progress_summary,
        'next_action': next_action,
        'recent_attachments': recent_attachments,
        'documents_count': sum(len(item['attachments']) for item in timeline_items),
        'help_chat_url': reverse('chat_thread_open', args=[trip.package_id]),
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
