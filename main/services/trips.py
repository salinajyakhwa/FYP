from django.utils import timezone

from ..forms import TripItemAttachmentForm
from ..models import Trip, TripItem
from .itineraries import _build_action_button_label


def _build_trip_timeline_items(trip):
    trip_items = (
        trip.items.select_related('package_day', 'selected_option')
        .prefetch_related('attachments', 'attachments__uploaded_by')
        .all()
        .order_by('day_number', 'sort_order', 'id')
    )

    return [
        {
            'id': item.id,
            'day_number': item.day_number,
            'title': item.title,
            'description': item.description,
            'status': item.get_status_display(),
            'status_key': item.status,
            'status_badge_class': {
                'pending': 'text-bg-light border',
                'ready': 'text-bg-info',
                'in_progress': 'text-bg-primary',
                'completed': 'text-bg-success',
                'blocked': 'text-bg-danger',
                'cancelled': 'text-bg-dark',
            }.get(item.status, 'text-bg-light border'),
            'item_card_class': {
                'pending': 'border',
                'ready': 'border border-info-subtle bg-info-subtle',
                'in_progress': 'border border-primary-subtle bg-primary-subtle',
                'completed': 'border border-success-subtle bg-success-subtle',
                'blocked': 'border border-danger-subtle bg-danger-subtle',
                'cancelled': 'border border-dark-subtle bg-light',
            }.get(item.status, 'border'),
            'action_link': item.action_link,
            'action_label': item.action_label or 'Open Link',
            'package_day_title': item.package_day.title if item.package_day else '',
            'selected_option_title': item.selected_option.title if item.selected_option else '',
            'option_type': item.selected_option.get_option_type_display() if item.selected_option else '',
            'vendor_notes': item.vendor_notes,
            'attachments': list(item.attachments.all()),
            'attachment_form': TripItemAttachmentForm(prefix=f'attachment-{item.id}'),
        }
        for item in trip_items
    ]


def _build_trip_progress_summary(trip):
    counts = {
        'total': 0,
        'pending': 0,
        'ready': 0,
        'in_progress': 0,
        'completed': 0,
        'blocked': 0,
        'cancelled': 0,
        'completion_percentage': 0,
    }

    for status in trip.items.values_list('status', flat=True):
        counts['total'] += 1
        if status in counts:
            counts[status] += 1

    if counts['total']:
        counts['completion_percentage'] = int((counts['completed'] / counts['total']) * 100)

    if counts['blocked']:
        counts['trip_health_label'] = 'Action Needed'
    elif counts['ready'] or counts['in_progress']:
        counts['trip_health_label'] = 'On Track'
    else:
        counts['trip_health_label'] = 'Waiting on Vendor'

    return counts


def _build_trip_next_action(timeline_items):
    priority_order = ['ready', 'in_progress', 'pending']
    for status_key in priority_order:
        for item in timeline_items:
            if item['status_key'] == status_key:
                return item
    return None


def _build_trip_recent_attachments(timeline_items, limit=4):
    attachments = []
    for item in timeline_items:
        for attachment in item['attachments']:
            attachments.append({
                'title': attachment.title,
                'type': attachment.get_attachment_type_display(),
                'url': attachment.file.url,
                'day_number': item['day_number'],
                'item_title': item['title'],
                'created_at': attachment.created_at,
            })

    attachments.sort(key=lambda entry: entry['created_at'], reverse=True)
    return attachments[:limit]


def _build_trip_timeline_sections(trip, timeline_items):
    today = timezone.now().date()
    current_day_number = None
    if trip.start_date:
        current_day_number = max(1, (today - trip.start_date).days + 1)

    today_items = []
    upcoming_items = []
    completed_items = []

    for item in timeline_items:
        if item['status_key'] in {'completed', 'cancelled'}:
            completed_items.append(item)
            continue

        if current_day_number is not None:
            if item['day_number'] <= current_day_number:
                today_items.append(item)
            else:
                upcoming_items.append(item)
        else:
            if item['status_key'] in {'ready', 'in_progress'}:
                today_items.append(item)
            else:
                upcoming_items.append(item)

    sections = []
    if today_items:
        sections.append({
            'title': 'Today',
            'subtitle': 'Most relevant items for the current stage of your trip.',
            'items': today_items,
        })
    if upcoming_items:
        sections.append({
            'title': 'Upcoming',
            'subtitle': 'What is coming next in your trip.',
            'items': upcoming_items,
        })
    if completed_items:
        sections.append({
            'title': 'Completed',
            'subtitle': 'Finished steps and completed history.',
            'items': completed_items,
        })

    return {
        'sections': sections,
        'current_day_number': current_day_number,
    }


def _create_trip_from_booking(booking):
    trip, _ = Trip.objects.get_or_create(
        booking=booking,
        defaults={
            'traveler': booking.user,
            'vendor': booking.package.vendor,
            'package': booking.package,
            'custom_itinerary': booking.custom_itinerary,
            'status': 'planned',
            'start_date': booking.package.start_date,
            'end_date': booking.package.end_date,
        },
    )

    trip_updates = []
    if trip.traveler_id != booking.user_id:
        trip.traveler = booking.user
        trip_updates.append('traveler')
    if trip.vendor_id != booking.package.vendor_id:
        trip.vendor = booking.package.vendor
        trip_updates.append('vendor')
    if trip.package_id != booking.package_id:
        trip.package = booking.package
        trip_updates.append('package')
    if trip.custom_itinerary_id != booking.custom_itinerary_id:
        trip.custom_itinerary = booking.custom_itinerary
        trip_updates.append('custom_itinerary')
    if trip.start_date != booking.package.start_date:
        trip.start_date = booking.package.start_date
        trip_updates.append('start_date')
    if trip.end_date != booking.package.end_date:
        trip.end_date = booking.package.end_date
        trip_updates.append('end_date')
    if trip_updates:
        trip.save(update_fields=trip_updates + ['updated_at'])

    existing_keys = set(
        trip.items.values_list('package_day_id', 'selected_option_id')
    )
    items_to_create = []

    if booking.custom_itinerary:
        selections = (
            booking.custom_itinerary.selections.select_related('package_day', 'selected_option')
            .all()
            .order_by('package_day__day_number', 'package_day__sort_order', 'id')
        )

        for selection in selections:
            item_key = (selection.package_day_id, selection.selected_option_id)
            if item_key in existing_keys:
                continue

            items_to_create.append(
                TripItem(
                    trip=trip,
                    package_day=selection.package_day,
                    selected_option=selection.selected_option,
                    title=selection.selected_option.title,
                    description=selection.selected_option.description or selection.package_day.description,
                    day_number=selection.package_day.day_number,
                    status='pending',
                    sort_order=selection.selected_option.sort_order,
                    action_link=selection.selected_option.action_link,
                    action_label=_build_action_button_label(selection.selected_option) or '',
                )
            )
    else:
        package_days = booking.package.package_days.all().order_by('day_number', 'sort_order', 'id')
        for package_day in package_days:
            item_key = (package_day.id, None)
            if item_key in existing_keys:
                continue

            items_to_create.append(
                TripItem(
                    trip=trip,
                    package_day=package_day,
                    selected_option=None,
                    title=package_day.title,
                    description=package_day.description,
                    day_number=package_day.day_number,
                    status='pending',
                    sort_order=package_day.sort_order,
                )
            )

    if items_to_create:
        TripItem.objects.bulk_create(items_to_create)

    return trip

