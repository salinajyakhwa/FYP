from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseBadRequest
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator # Added for pagination
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import EmailMessage
from django.utils import timezone
from django.db.models.functions import TruncMonth
from decimal import Decimal
import base64
import hashlib 
import hmac
import json
import logging
import uuid
from django.contrib.auth import get_user_model # Replaced direct User import
import stripe
from django.conf import settings
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
import csv
from django.http import HttpResponse
from.models import Booking, TravelPackage, CustomItinerarySelection
from .utils import send_otp
from .models import EmailOTP


# Models
from .models import (
    TravelPackage,
    PackageDay,
    PackageDayOption,
    CustomItinerary,
    CustomItinerarySelection,
    Notification,
    Trip,
    TripItem,
    TripItemAttachment,
    ChatThread,
    ChatMessage,
    Booking,
    Review,
    UserProfile,
    Vendor,
    Vehicle,
)

User = get_user_model() # Get the User model

# Forms
from .forms import (
    ReviewForm, 
    ItineraryDayForm,
    ItineraryFormSet, 
    PackageDayForm,
    PackageDayOptionForm,
    CustomItinerarySelectionForm,
    TripItemVendorNotesForm,
    TripItemAttachmentForm,
    ChatMessageForm,
    TravelPackageForm, 
    UserUpdateForm, 
    UserProfileUpdateForm,
    PasswordChangeForm,
    CustomAuthenticationForm,
    CustomUserCreationForm # Ensure this is in your forms.py
)

# Decorators
from .decorators import role_required
from .notifications import create_notification, mark_notification_read

logger = logging.getLogger(__name__)

# ==========================================
# 1. PUBLIC VIEWS (Landing, About, Listings)
# ==========================================

# New view for the root URL to handle redirection
def root_redirect_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('admin_dashboard')
        if hasattr(request.user, 'userprofile'):
            if request.user.userprofile.role == 'admin':
                return redirect('admin_dashboard')
            if request.user.userprofile.role == 'vendor':
                return redirect('vendor_dashboard')
        # Default for logged-in travelers
        return redirect('dashboard')
    # Default for non-logged-in users
    return redirect('dashboard')

def home(request):
    today = timezone.now().date()
    sponsored_packages = TravelPackage.objects.select_related('vendor').filter(
        is_sponsored=True,
        sponsorship_start__isnull=False,
        sponsorship_end__isnull=False,
        sponsorship_start__lte=today,
        sponsorship_end__gte=today,
    ).order_by('-sponsorship_priority', '-created_at')[:4]
    packages = (
        TravelPackage.objects.select_related('vendor')
        .exclude(id__in=sponsored_packages.values_list('id', flat=True))
        .order_by('-created_at')[:4]
    )
    
    return render(request, 'main/home.html', {
        'packages': packages,
        'sponsored_packages': sponsored_packages,
    })

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


def _sync_package_itinerary_json(package):
    package_days = package.package_days.prefetch_related('options').all()
    package.itinerary = [
        {
            'day': package_day.day_number,
            'title': package_day.title,
            'activity_type': 'travel',
            'description': package_day.description,
            'inclusions': ', '.join(option.title for option in package_day.options.all()),
        }
        for package_day in package_days
    ]
    package.save(update_fields=['itinerary', 'updated_at'])


def _build_selected_options_summary(selected_options):
    return [
        {
            'day_number': package_day.day_number,
            'day_title': package_day.title,
            'option_title': selected_option.title,
            'option_type': selected_option.get_option_type_display(),
            'additional_cost': selected_option.additional_cost,
            'description': selected_option.description,
        }
        for package_day, selected_option in selected_options
    ]


def _build_action_button_label(option):
    if not option.action_link:
        return None
    if option.option_type == 'flight':
        return 'Book Flight'

    title = (option.title or '').strip()
    if title and len(title) <= 30:
        return f'Open {title}'
    return 'Open Link'


def _build_group_title(items, action_link):
    if not items:
        return 'Selections'

    if action_link:
        option_type_keys = {item['option_type_key'] for item in items}
        if option_type_keys == {'flight'}:
            return 'Flights'
        if option_type_keys == {'stay'}:
            return 'Stays'
        if option_type_keys == {'activity'}:
            return 'Activities'
        if len(items) > 1:
            return 'Shared Actions'

    if len(items) == 1:
        return f"Day {items[0]['day_number']}"
    return 'Selections'


def _build_booking_selection_items(custom_itinerary):
    if not custom_itinerary:
        return []

    selections = (
        custom_itinerary.selections.select_related('package_day', 'selected_option')
        .all()
        .order_by('package_day__day_number', 'package_day__sort_order', 'id')
    )

    return [
        {
            'day_number': selection.package_day.day_number,
            'day_title': selection.package_day.title,
            'day_description': selection.package_day.description,
            'option_title': selection.selected_option.title,
            'option_type_key': selection.selected_option.option_type,
            'option_type': selection.selected_option.get_option_type_display(),
            'option_description': selection.selected_option.description,
            'selected_price': selection.selected_price,
            'action_link': selection.selected_option.action_link,
            'action_button_label': _build_action_button_label(selection.selected_option),
        }
        for selection in selections
    ]


def _group_booking_selection_items(selection_items):
    groups = []
    index_by_link = {}

    for item in selection_items:
        action_link = item['action_link']
        if action_link:
            group_index = index_by_link.get(action_link)
            if group_index is None:
                groups.append({
                    'group_key': action_link,
                    'group_link': action_link,
                    'group_button_label': item['action_button_label'] or 'Open Link',
                    'items': [],
                })
                index_by_link[action_link] = len(groups) - 1
                group_index = index_by_link[action_link]
            groups[group_index]['items'].append(item)
        else:
            groups.append({
                'group_key': f"ungrouped-{len(groups)}",
                'group_link': None,
                'group_button_label': None,
                'items': [item],
            })

    for group in groups:
        group['group_title'] = _build_group_title(group['items'], group['group_link'])

    return groups


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


def _build_traveler_dashboard_summary(user):
    active_trips = list(
        Trip.objects.filter(traveler=user)
        .exclude(status__in=['completed', 'cancelled'])
        .only('id', 'start_date')
    )
    unread_notifications = Notification.objects.filter(user=user, is_read=False).count()

    pending_actions = 0
    upcoming_items = 0
    today = timezone.now().date()

    for trip in active_trips:
        current_day_number = None
        if trip.start_date:
            current_day_number = max(1, (today - trip.start_date).days + 1)

        trip_items = (
            trip.items.only('day_number', 'status')
            .exclude(status__in=['completed', 'cancelled'])
            .all()
        )
        for item in trip_items:
            is_upcoming = current_day_number is not None and item.day_number > current_day_number
            if is_upcoming:
                upcoming_items += 1
            elif item.status in {'ready', 'in_progress', 'blocked', 'pending'}:
                pending_actions += 1

    return {
        'active_trips': len(active_trips),
        'unread_notifications': unread_notifications,
        'pending_actions': pending_actions,
        'upcoming_items': upcoming_items,
    }


def _build_dashboard_trip_cards(user, limit=4):
    today = timezone.now().date()
    trips = list(
        Trip.objects.filter(traveler=user)
        .exclude(status__in=['completed', 'cancelled'])
        .select_related('booking', 'package', 'vendor')
    )

    cards = []
    for trip in trips:
        timeline_items = _build_trip_timeline_items(trip)
        progress_summary = _build_trip_progress_summary(trip)
        next_action = _build_trip_next_action(timeline_items)

        if trip.status == 'in_progress':
            lifecycle_sort = 0
            lifecycle_label = 'Live Now'
        elif trip.start_date and trip.start_date <= today:
            lifecycle_sort = 1
            lifecycle_label = 'Current Trip'
        elif trip.status == 'ready':
            lifecycle_sort = 2
            lifecycle_label = 'Ready Soon'
        else:
            lifecycle_sort = 3
            lifecycle_label = 'Upcoming'

        cards.append({
            'trip': trip,
            'progress_summary': progress_summary,
            'next_action': next_action,
            'lifecycle_label': lifecycle_label,
            'lifecycle_sort': lifecycle_sort,
        })

    cards.sort(
        key=lambda entry: (
            entry['lifecycle_sort'],
            entry['trip'].start_date or timezone.datetime.max.date(),
            entry['trip'].created_at,
        )
    )
    return cards[:limit]


def _build_dashboard_next_actions(user, limit=6):
    trip_cards = _build_dashboard_trip_cards(user, limit=20)
    action_cards = []

    for card in trip_cards:
        next_action = card['next_action']
        if not next_action:
            continue

        action_priority = {
            'blocked': 0,
            'ready': 1,
            'in_progress': 2,
            'pending': 3,
        }.get(next_action['status_key'], 4)

        action_cards.append({
            'trip': card['trip'],
            'package': card['trip'].package,
            'vendor': card['trip'].vendor,
            'lifecycle_label': card['lifecycle_label'],
            'day_number': next_action['day_number'],
            'title': next_action['title'],
            'selected_option_title': next_action['selected_option_title'],
            'status': next_action['status'],
            'status_key': next_action['status_key'],
            'action_link': next_action['action_link'],
            'action_label': next_action['action_label'],
            'description': next_action['description'],
            'action_priority': action_priority,
        })

    action_cards.sort(
        key=lambda entry: (
            entry['action_priority'],
            entry['trip'].start_date or timezone.datetime.max.date(),
            entry['day_number'],
        )
    )
    return action_cards[:limit]


def _build_payment_context(*, package, custom_itinerary=None):
    amount = custom_itinerary.final_price if custom_itinerary else package.price
    return {
        'package': package,
        'custom_itinerary': custom_itinerary,
        'amount': amount,
        'display_name': f"{package.name} (Custom Itinerary)" if custom_itinerary else package.name,
    }


SPONSORSHIP_DEFAULT_PRICE = Decimal('100.00')
SPONSORSHIP_DURATION_DAYS = 30


def _get_sponsorship_price(package):
    amount = Decimal(package.sponsorship_amount or 0)
    return amount if amount > 0 else SPONSORSHIP_DEFAULT_PRICE


def _build_sponsorship_payment_context(package):
    amount = _get_sponsorship_price(package)
    return {
        'package': package,
        'sponsorship_package': package,
        'amount': amount,
        'display_name': f"{package.name} Sponsorship",
        'sponsorship_duration_days': SPONSORSHIP_DURATION_DAYS,
    }


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
    counterpart_name = thread.traveler.username if recipient.id == _get_vendor_user(thread.vendor).id else thread.vendor.name

    create_notification(
        user=recipient,
        title='New chat message',
        message=f"{message_obj.sender.username} sent you a new message about {thread.package.name if thread.package else 'your trip'}.",
        notification_type='chat_message',
        target_url=reverse('chat_thread_detail', args=[thread.id]),
        related_thread=thread,
    )


def _store_pending_payment_session(request, *, package_id=None, custom_itinerary_id=None, sponsorship_package_id=None, transaction_uuid=None, provider=None):
    request.session['pending_booking_package_id'] = package_id
    request.session['pending_custom_itinerary_id'] = custom_itinerary_id
    request.session['pending_sponsorship_package_id'] = sponsorship_package_id
    request.session['pending_payment_provider'] = provider
    request.session['pending_payment_transaction_uuid'] = transaction_uuid


def _clear_pending_payment_session(request):
    for key in [
        'pending_booking_package_id',
        'pending_custom_itinerary_id',
        'pending_sponsorship_package_id',
        'pending_payment_provider',
        'pending_payment_transaction_uuid',
    ]:
        request.session.pop(key, None)


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


def _create_or_update_booking_from_pending_payment(request):
    custom_itinerary_id = request.session.get('pending_custom_itinerary_id')
    package_id = request.session.get('pending_booking_package_id')

    if not custom_itinerary_id and not package_id:
        raise ValueError('No pending payment target found.')

    if custom_itinerary_id:
        custom_itinerary = get_object_or_404(
            CustomItinerary.objects.select_related('package'),
            pk=custom_itinerary_id,
            user=request.user,
        )

        booking, _ = Booking.objects.get_or_create(
            custom_itinerary=custom_itinerary,
            defaults={
                'user': request.user,
                'package': custom_itinerary.package,
                'number_of_travelers': 1,
                'total_price': custom_itinerary.final_price,
                'status': 'confirmed',
            }
        )
        if booking.status != 'confirmed' or booking.total_price != custom_itinerary.final_price:
            booking.status = 'confirmed'
            booking.total_price = custom_itinerary.final_price
            booking.package = custom_itinerary.package
            booking.user = request.user
            booking.save(update_fields=['status', 'total_price', 'package', 'user'])
        if custom_itinerary.status != 'confirmed':
            custom_itinerary.status = 'confirmed'
            custom_itinerary.save(update_fields=['status', 'updated_at'])

        _create_trip_from_booking(booking)

        return booking, custom_itinerary.package, True

    package = get_object_or_404(TravelPackage, pk=package_id)
    booking = Booking.objects.create(
        user=request.user,
        package=package,
        number_of_travelers=1,
        total_price=package.price,
        status='confirmed'
    )
    _create_trip_from_booking(booking)
    return booking, package, False


def _activate_pending_sponsorship(request):
    sponsorship_package_id = request.session.get('pending_sponsorship_package_id')
    if not sponsorship_package_id:
        raise ValueError('No pending sponsorship target found.')

    vendor = _get_vendor_or_403(request)
    package = get_object_or_404(
        TravelPackage.objects.select_related('vendor'),
        pk=sponsorship_package_id,
        vendor=vendor,
    )

    today = timezone.now().date()
    current_price = _get_sponsorship_price(package)

    if package.is_sponsored and package.sponsorship_end and package.sponsorship_end >= today:
        start_anchor = package.sponsorship_end + timezone.timedelta(days=1)
        if not package.sponsorship_start:
            package.sponsorship_start = today
    else:
        package.is_sponsored = True
        package.sponsorship_start = today
        start_anchor = today

    package.sponsorship_end = start_anchor + timezone.timedelta(days=SPONSORSHIP_DURATION_DAYS - 1)
    package.sponsorship_amount = current_price
    if package.sponsorship_priority == 0:
        package.sponsorship_priority = 1
    package.save(update_fields=[
        'is_sponsored',
        'sponsorship_start',
        'sponsorship_end',
        'sponsorship_amount',
        'sponsorship_priority',
        'updated_at',
    ])

    create_notification(
        user=_get_vendor_user(vendor),
        title='Sponsorship activated',
        message=f"{package.name} is sponsored through {package.sponsorship_end}.",
        notification_type='payment_success',
        target_url=reverse('vendor_package_list'),
        dedupe_key=f"sponsorship:{package.id}:{package.sponsorship_end.isoformat()}",
    )

    return package


def _generate_esewa_signature(total_amount, transaction_uuid, product_code):
    message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
    digest = hmac.new(
        settings.ESEWA_SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode('utf-8')


def _verify_esewa_payload(payload):
    signed_field_names = payload.get('signed_field_names', '')
    signature = payload.get('signature')

    if not signed_field_names or not signature:
        return False

    message = ','.join(
        f"{field}={payload.get(field, '')}"
        for field in signed_field_names.split(',')
    )
    expected_signature = base64.b64encode(
        hmac.new(
            settings.ESEWA_SECRET_KEY.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256,
        ).digest()
    ).decode('utf-8')
    return hmac.compare_digest(signature, expected_signature)

def about(request):
    return render(request, 'main/about.html')

def search_results(request):
    query = request.GET.get('q', '')
    if query:
        packages = TravelPackage.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(vendor__name__icontains=query)
        )
    else:
        packages = TravelPackage.objects.all()
    
    return render(request, 'main/_package_list_partial.html', {'packages': packages})

from .filters import TravelPackageFilter

def package_list(request):
    packages_list = TravelPackage.objects.select_related('vendor').all().order_by('-created_at')
    package_filter = TravelPackageFilter(request.GET, queryset=packages_list)
    today = timezone.now().date()
    filtered_qs = package_filter.qs.select_related('vendor')
    sponsored_packages = filtered_qs.filter(
        is_sponsored=True,
        sponsorship_start__isnull=False,
        sponsorship_end__isnull=False,
        sponsorship_start__lte=today,
        sponsorship_end__gte=today,
    ).order_by('-sponsorship_priority', '-created_at')

    organic_packages_qs = filtered_qs.exclude(id__in=sponsored_packages.values_list('id', flat=True)).order_by('-created_at')

    paginator = Paginator(organic_packages_qs, 9) # Show 9 packages per page
    page_number = request.GET.get('page')
    packages = paginator.get_page(page_number)

    context = {
        'packages': packages,
        'filter': package_filter,
        'sponsored_packages': sponsored_packages,
    }
    return render(request, 'main/package_list.html', context)

def package_detail(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    reviews = Review.objects.filter(package=package).order_by('-created_at')
    review_form = ReviewForm()
    itinerary_items = []
    profile = getattr(request.user, 'userprofile', None) if request.user.is_authenticated else None
    profile_vendor = getattr(profile, 'vendor', None) if profile else None
    is_vendor_owner = bool(
        request.user.is_authenticated
        and profile
        and profile.role == 'vendor'
        and profile_vendor
        and profile_vendor.id == package.vendor_id
    )
    package_days = package.package_days.prefetch_related('options').all()
    customization_form = CustomItinerarySelectionForm(package=package) if package_days.exists() else None
    selected_options_summary = []
    customization_extra_cost = Decimal('0.00')
    customization_total = Decimal(package.price)

    if package_days.exists():
        if request.method == 'POST' and (
            'preview_customization' in request.POST or 'save_customization' in request.POST
        ):
            customization_form = CustomItinerarySelectionForm(request.POST, package=package)
            if customization_form.is_valid():
                selected_options = customization_form.get_selected_options()
                customization_total = customization_form.calculate_total(package.price)
                customization_extra_cost = customization_total - Decimal(package.price)
                selected_options_summary = _build_selected_options_summary(selected_options)

                if 'save_customization' in request.POST:
                    if not request.user.is_authenticated:
                        messages.info(request, 'Log in to save a custom itinerary.')
                        return redirect(f"{reverse('login')}?next={request.path}")

                    with transaction.atomic():
                        custom_itinerary = CustomItinerary.objects.create(
                            user=request.user,
                            package=package,
                            base_price=package.price,
                            final_price=customization_total,
                            status='submitted',
                        )
                        CustomItinerarySelection.objects.bulk_create([
                            CustomItinerarySelection(
                                custom_itinerary=custom_itinerary,
                                package_day=package_day,
                                selected_option=selected_option,
                                selected_price=selected_option.additional_cost,
                            )
                            for package_day, selected_option in selected_options
                        ])

                    _notify_custom_itinerary_saved(custom_itinerary)
                    messages.success(request, 'Custom itinerary saved successfully.')
                    return redirect('custom_itinerary_detail', custom_itinerary_id=custom_itinerary.id)

        for package_day in package_days:
            selection_field = None
            if customization_form is not None:
                field_name = f'day_{package_day.id}'
                if field_name in customization_form.fields:
                    selection_field = customization_form[field_name]

            itinerary_items.append({
                'id': package_day.id,
                'day': package_day.day_number,
                'title': package_day.title,
                'description': package_day.description,
                'activity_label': 'Day Plan',
                'inclusions': [],
                'options': list(package_day.options.all()),
                'selection_field': selection_field,
            })
    else:
        activity_labels = dict(ItineraryDayForm.ACTIVITY_CHOICES)
        raw_itinerary_items = package.itinerary if isinstance(package.itinerary, list) else []

        for item in sorted(raw_itinerary_items, key=lambda entry: entry.get('day') or 0):
            if not isinstance(item, dict):
                continue

            day = item.get('day')
            title = (item.get('title') or '').strip()
            description = (item.get('description') or '').strip()
            activity_type = item.get('activity_type') or ''
            inclusions = [
                inclusion.strip()
                for inclusion in (item.get('inclusions') or '').split(',')
                if inclusion.strip()
            ]

            if not day or not title or not description:
                continue

            itinerary_items.append({
                'day': day,
                'title': title,
                'description': description,
                'activity_label': activity_labels.get(activity_type, activity_type.replace('_', ' ').title()),
                'inclusions': inclusions,
                'options': [],
                'selection_field': None,
            })
    
    user_can_review = False
    if request.user.is_authenticated:
        # Check if user has a confirmed booking for a completed trip AND has not already reviewed
        completed_booking_exists = Booking.objects.filter(
            user=request.user,
            package=package,
            status='confirmed',
            package__end_date__lt=timezone.now().date()
        ).exists()

        if completed_booking_exists:
            has_already_reviewed = Review.objects.filter(user=request.user, package=package).exists()
            if not has_already_reviewed:
                user_can_review = True
            
    context = {
        'package': package,
        'reviews': reviews,
        'user_can_review': user_can_review,
        'review_form': review_form,
        'itinerary_items': itinerary_items,
        'customization_form': customization_form,
        'selected_options_summary': selected_options_summary,
        'customization_extra_cost': customization_extra_cost,
        'customization_total': customization_total,
        'is_vendor_owner': is_vendor_owner,
    }
    return render(request, 'main/package_detail.html', context)


@login_required
def custom_itinerary_detail(request, custom_itinerary_id):
    custom_itinerary = get_object_or_404(
        CustomItinerary.objects.select_related('package', 'package__vendor', 'user').prefetch_related(
            'selections__package_day',
            'selections__selected_option',
        ),
        pk=custom_itinerary_id,
    )

    if custom_itinerary.user != request.user:
        raise PermissionDenied

    context = {
        'custom_itinerary': custom_itinerary,
        'selections': custom_itinerary.selections.all(),
        'payment_context': _build_payment_context(
            package=custom_itinerary.package,
            custom_itinerary=custom_itinerary,
        ),
    }
    return render(request, 'main/custom_itinerary_detail.html', context)


@login_required
def chat_thread_open(request, package_id):
    package = get_object_or_404(
        TravelPackage.objects.select_related('vendor', 'vendor__user_profile', 'vendor__user_profile__user'),
        pk=package_id,
    )

    profile = getattr(request.user, 'userprofile', None)
    if not profile or profile.role != 'traveler':
        raise PermissionDenied

    thread, _ = ChatThread.objects.get_or_create(
        traveler=request.user,
        vendor=package.vendor,
        package=package,
        defaults={
            'booking': None,
            'custom_itinerary': None,
        }
    )
    return redirect('chat_thread_detail', thread_id=thread.id)


@login_required
def chat_thread_list(request):
    profile = getattr(request.user, 'userprofile', None)
    if not profile:
        raise PermissionDenied

    if profile.role == 'traveler':
        threads = ChatThread.objects.filter(
            traveler=request.user,
            is_active=True,
        ).select_related(
            'vendor',
            'vendor__user_profile',
            'vendor__user_profile__user',
            'package',
        ).prefetch_related('messages__sender')
    elif profile.role == 'vendor':
        vendor = _get_vendor_or_403(request)
        threads = ChatThread.objects.filter(
            vendor=vendor,
            is_active=True,
        ).select_related(
            'traveler',
            'package',
        ).prefetch_related('messages__sender')
    else:
        raise PermissionDenied

    context = {
        'threads': threads,
        'user_role': profile.role,
    }
    return render(request, 'main/chat_thread_list.html', context)


@login_required
def chat_thread_detail(request, thread_id):
    thread = _get_chat_thread_for_user_or_403(request.user, thread_id)
    messages_qs = thread.messages.select_related('sender').all()

    if request.method == 'POST':
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.thread = thread
            message.sender = request.user
            message.save()
            ChatThread.objects.filter(pk=thread.id).update(updated_at=timezone.now())
            _notify_chat_message(message)
            return redirect('chat_thread_detail', thread_id=thread.id)
    else:
        form = ChatMessageForm()

    counterpart_name = thread.vendor.name if thread.traveler_id == request.user.id else thread.traveler.username
    context = {
        'thread': thread,
        'messages': messages_qs,
        'form': form,
        'counterpart_name': counterpart_name,
    }
    return render(request, 'main/chat_thread_detail.html', context)


@login_required
def choose_payment(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    return render(request, 'main/choose_payment.html', _build_payment_context(package=package))


@login_required
def choose_custom_itinerary_payment(request, custom_itinerary_id):
    custom_itinerary = get_object_or_404(
        CustomItinerary.objects.select_related('package'),
        pk=custom_itinerary_id,
        user=request.user,
    )
    return render(
        request,
        'main/choose_payment.html',
        _build_payment_context(package=custom_itinerary.package, custom_itinerary=custom_itinerary),
    )


@login_required
@role_required(allowed_roles=['vendor'])
def choose_sponsorship_payment(request, package_id):
    package = get_object_or_404(
        TravelPackage.objects.select_related('vendor'),
        pk=package_id,
        vendor=_get_vendor_or_403(request),
    )
    return render(request, 'main/choose_payment.html', _build_sponsorship_payment_context(package))

def compare_packages(request):
    def _find_similar_packages(base_package, limit=3):
        base_queryset = TravelPackage.objects.exclude(id=base_package.id)
        similarity_score = Case(
            When(travel_type=base_package.travel_type, then=Value(3)),
            default=Value(0),
            output_field=IntegerField(),
        ) + Case(
            When(location=base_package.location, then=Value(2)),
            default=Value(0),
            output_field=IntegerField(),
        ) + Case(
            When(price__gte=base_package.price * Decimal('0.80'), price__lte=base_package.price * Decimal('1.20'), then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )

        deluxe_q = Q(name__icontains='deluxe') | Q(description__icontains='deluxe') | Q(travel_type__icontains='deluxe')
        base_is_deluxe = TravelPackage.objects.filter(id=base_package.id).filter(deluxe_q).exists()

        if base_is_deluxe:
            base_queryset = base_queryset.filter(deluxe_q)

        return list(
            base_queryset
            .annotate(similarity_score=similarity_score)
            .order_by('-similarity_score', '-created_at')[:limit]
        )

    if request.method == 'GET' and request.GET.get('package_id'):
        base_package = get_object_or_404(TravelPackage, id=request.GET.get('package_id'))
        similar_packages = _find_similar_packages(base_package)
        packages = [base_package] + similar_packages
        return render(request, 'main/compare_packages.html', {
            'packages': packages,
            'base_package': base_package,
            'auto_generated': True,
        })

    if request.method == 'POST':
        package_ids = request.POST.getlist('package_ids')
        if not package_ids:
            messages.warning(request, "Select at least one package to compare.")
            return redirect('package_list')

        selected_packages = list(TravelPackage.objects.filter(id__in=package_ids))

        if len(selected_packages) == 1:
            base_package = selected_packages[0]
            packages = [base_package] + _find_similar_packages(base_package)
            messages.info(request, "Showing similar packages automatically based on your selected package.")
            return render(request, 'main/compare_packages.html', {
                'packages': packages,
                'base_package': base_package,
                'auto_generated': True,
            })

        return render(request, 'main/compare_packages.html', {
            'packages': selected_packages,
            'auto_generated': False,
        })

    return redirect('package_list')

# ==========================================
# 2. AUTHENTICATION
# ==========================================

class CustomLoginView(auth_views.LoginView):
    template_name = 'main/login.html'
    authentication_form = CustomAuthenticationForm

def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            email = form.cleaned_data['email']

            send_otp(email, user)

            request.session['pending_email'] = email
            request.session['pending_user_id'] = user.id
            messages.success(request, f"An OTP has been sent to {email}. Please enter it to complete registration.")
            return redirect('verify_otp')
    else:
        form = CustomUserCreationForm()
    return render(request, 'main/register.html', {'form': form})



def verify_otp(request):
    pending_email = request.session.get('pending_email')
    pending_user_id = request.session.get('pending_user_id')

    if not pending_email or not pending_user_id:
        messages.info(request, 'Start registration first to verify your email.')
        return redirect('register')

    if request.method == 'POST':
        otp = request.POST.get('otp', '').strip()
        otp_obj = (
            EmailOTP.objects
            .filter(email=pending_email, otp=otp, user_id=pending_user_id)
            .order_by('-created_at')
            .first()
        )

        if otp_obj and otp_obj.is_valid():
            user = get_object_or_404(User, pk=pending_user_id, email=pending_email)
            profile = get_object_or_404(UserProfile, user=user)
            user.is_active = True
            user.save(update_fields=['is_active'])
            profile.is_verified = True
            profile.save(update_fields=['is_verified'])

            EmailOTP.objects.filter(email=pending_email, user_id=pending_user_id).delete()
            request.session.pop('pending_email', None)
            request.session.pop('pending_user_id', None)

            vendor = getattr(profile, 'vendor', None)
            if profile.role == 'vendor' and vendor:
                vendor.status = 'pending'
                vendor.save(update_fields=['status'])
                messages.success(
                    request,
                    'Your email is verified. Your vendor application has been submitted for admin review.'
                )
                return redirect('login')

            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Your account has been verified successfully.')
            return redirect('dashboard')

        return render(
            request,
            'main/verify_otp.html',
            {
                'email': pending_email,
                'error': 'Invalid or expired OTP. Please try again.',
            },
        )

    return render(request, 'main/verify_otp.html', {'email': pending_email})

# ==========================================
# 3. PRIVATE USER VIEWS (Dashboard, Profile)
# ==========================================

@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect('admin_dashboard')

    if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'admin':
        return redirect('admin_dashboard')

    # Redirect vendors to vendor dashboard
    if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'vendor':
        return redirect('vendor_dashboard')

    recent_bookings = list(
        Booking.objects.filter(user=request.user)
        .select_related('package', 'package__vendor', 'trip')
        .order_by('-booking_date')[:5]
    )

    recent_notifications = list(
        Notification.objects.filter(user=request.user)
        .order_by('-created_at')[:5]
    )

    recent_threads = list(
        ChatThread.objects.filter(traveler=request.user, is_active=True)
        .select_related('vendor', 'package')
        .prefetch_related('messages__sender')
        .order_by('-updated_at')[:5]
    )
    for thread in recent_threads:
        messages_list = list(thread.messages.all())
        thread.latest_message = messages_list[-1] if messages_list else None

    saved_custom_itineraries = list(
        CustomItinerary.objects.filter(user=request.user)
        .exclude(status='confirmed')
        .select_related('package', 'package__vendor')
        .order_by('-created_at')[:4]
    )

    context = {
        'dashboard_summary': _build_traveler_dashboard_summary(request.user),
        'active_trip_cards': _build_dashboard_trip_cards(request.user),
        'next_actions': _build_dashboard_next_actions(request.user),
        'recent_notifications': recent_notifications,
        'recent_threads': recent_threads,
        'saved_custom_itineraries': saved_custom_itineraries,
        'recent_bookings': recent_bookings,
    }
    return render(request, 'main/traveler_dashboard.html', context)

@login_required
def profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        if 'update_profile' in request.POST:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            profile_form = UserProfileUpdateForm(request.POST, request.FILES, instance=profile)
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Your profile has been updated!')
                return redirect('profile')
        
        elif 'change_password' in request.POST:
            pass_form = PasswordChangeForm(request.user, request.POST)
            if pass_form.is_valid():
                user = pass_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Your password was successfully updated!')
                return redirect('profile')
            else:
                messages.error(request, 'Please correct the password error below.')

    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = UserProfileUpdateForm(instance=profile)
        pass_form = PasswordChangeForm(request.user)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'pass_form': pass_form
    }
    return render(request, 'main/profile.html', context)

@login_required
def my_bookings(request):
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related('package', 'package__vendor', 'custom_itinerary', 'trip')
        .prefetch_related(
            'custom_itinerary__selections__package_day',
            'custom_itinerary__selections__selected_option',
        )
        .order_by('-booking_date')
    )
    for booking in bookings:
        booking.selection_items = _build_booking_selection_items(booking.custom_itinerary)
        booking.selection_groups = _group_booking_selection_items(booking.selection_items)
    return render(request, 'main/my_bookings.html', {'bookings': bookings})


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).select_related(
        'related_booking',
        'related_custom_itinerary',
        'related_thread',
        'related_trip',
    )
    return render(request, 'main/notifications.html', {'notifications': notifications})


@login_required
def mark_notification_read_view(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    mark_notification_read(notification)
    target_url = notification.target_url or reverse('notification_list')
    return redirect(target_url)


@login_required
def mark_all_notifications_read(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    now = timezone.now()
    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True,
        read_at=now,
    )
    messages.success(request, 'All notifications marked as read.')
    return redirect('notification_list')


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

    context = {
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
    }
    return render(request, 'main/trip_dashboard.html', context)


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

    context = {
        'trip': trip,
        'booking': trip.booking,
        'package': trip.package,
        'traveler': trip.traveler,
        'timeline_items': _build_trip_timeline_items(trip),
        'progress_summary': _build_trip_progress_summary(trip),
    }
    return render(request, 'main/vendor_trip_dashboard.html', context)


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
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)

    if booking.user != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        if booking.status in ['pending', 'confirmed']:
            booking.status = 'cancelled'
            booking.save()
            messages.success(request, 'Booking cancelled successfully.')
        else:
            messages.error(request, 'This booking cannot be cancelled.')
    
    return redirect('my_bookings')

@login_required
def add_review(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    
    # Server-side check for existing review
    if Review.objects.filter(user=request.user, package=package).exists():
        messages.error(request, 'You have already submitted a review for this package.')
        return redirect('package_detail', package_id=package.id)

    # Server-side check to ensure user has a completed, confirmed booking
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
            review.is_verified = True # The checks above imply verification
            review.save()
            messages.success(request, 'Thank you for your review!')
            return redirect('package_detail', package_id=package.id)
            
    # Redirect if not a POST request or form is invalid
    return redirect('package_detail', package_id=package.id)

# --- NEW FUNCTION FOR EMAIL VERIFICATION ---
def send_verification_email(request, user, profile):
    current_site = get_current_site(request)
    mail_subject = "Activate your account."
    message = render_to_string('main/acc_active_email.html', {
        'user': user,
        'domain': current_site.domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': profile.verification_token, # Use the token from the UserProfile
    })
    to_email = user.email
    email = EmailMessage(
        mail_subject, message, to=[to_email]
    )
    email.send()

# --- NEW VIEW FOR EMAIL VERIFICATION ---
def check_email(request):
    return render(request, 'main/check_email.html')

def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None:
        profile = UserProfile.objects.get(user=user)
        if profile.verification_token == token and (timezone.now() - profile.token_created_at).total_seconds() < 3600: # Token valid for 1 hour
            user.is_active = True
            user.save()
            profile.is_verified = True
            profile.verification_token = None
            profile.token_created_at = None
            profile.save()
            login(request, user)
            messages.success(request, 'Your account has been activated!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Activation link is invalid or expired!')
    else:
        messages.error(request, 'Activation link is invalid!')

    return render(request, 'main/verification_status.html')

# ==========================================
# 4. VENDOR VIEWS
# ==========================================

@login_required
@role_required(allowed_roles=['vendor'])
def vendor_dashboard(request):
    vendor = _get_vendor_or_403(request)
    
    # === Sales Data Calculation ===
    confirmed_bookings = Booking.objects.filter(package__vendor=vendor, status='confirmed')

    # 1. Total Revenue and Bookings
    total_stats = confirmed_bookings.aggregate(
        total_revenue=Sum('total_price'),
        total_bookings=Count('id')
    )
    total_revenue = total_stats.get('total_revenue') or 0
    total_bookings_count = total_stats.get('total_bookings') or 0

    # 2. Monthly Revenue Chart Data (for the last 12 months)
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

    # 3. Bookings per Package Chart Data (Top 5 packages)
    package_booking_data = confirmed_bookings.values('package__name').annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    package_labels = [item['package__name'] for item in package_booking_data]
    package_values = [item['count'] for item in package_booking_data]

    # 4. Recent Bookings for the table
    recent_bookings = Booking.objects.filter(package__vendor=vendor).order_by('-booking_date')[:5]

    context = {
        'total_revenue': total_revenue,
        'total_bookings_count': total_bookings_count,
        'monthly_revenue_labels': json.dumps(monthly_labels),
        'monthly_revenue_values': json.dumps(monthly_values),
        'package_booking_labels': json.dumps(package_labels),
        'package_booking_values': json.dumps(package_values),
        'recent_bookings': recent_bookings,
    }
    return render(request, 'main/vendor_dashboard.html', context)

@login_required
@role_required(allowed_roles=['vendor'])
def vendor_bookings(request):
    vendor = _get_vendor_or_403(request)

    bookings = Booking.objects.filter(package__vendor=vendor)\
        .select_related('user', 'package', 'custom_itinerary', 'trip')\
        .prefetch_related(
            'custom_itinerary__selections__package_day',
            'custom_itinerary__selections__selected_option'
        )\
        .order_by('-booking_date')

    for booking in bookings:
        booking.selection_items = _build_booking_selection_items(booking.custom_itinerary)
        booking.selection_groups = _group_booking_selection_items(booking.selection_items)

    context = {
        'bookings': bookings,
    }

    return render(request, 'main/vendor_bookings.html', context)

@login_required
@role_required(allowed_roles=['vendor'])
def update_booking_status(request, booking_id, new_status):
    vendor = _get_vendor_or_403(request)
    booking = get_object_or_404(Booking, id=booking_id, package__vendor=vendor)

    if request.method == 'POST':
        if new_status in ['confirmed', 'cancelled']:
            booking.status = new_status
            booking.save()
            messages.success(request, f"Booking status updated to {new_status}.")
        else:
            messages.error(request, "Invalid status.")
    
    return redirect('vendor_bookings')

@login_required
@role_required(allowed_roles=['vendor'])
def vendor_package_list(request):
    vendor = _get_vendor_or_403(request)
    packages = TravelPackage.objects.filter(vendor=vendor).order_by('-created_at')
    
    context = {
        'packages': packages
    }
    return render(request, 'main/vendor_package_list.html', context)

@login_required
@role_required(allowed_roles=['vendor'])
def create_package(request):
    if request.method == 'POST':
        form = TravelPackageForm(request.POST, request.FILES) # Added request.FILES for images
        if form.is_valid():
            package = form.save(commit=False)
            package.vendor = _get_vendor_or_403(request)
            package.save()
            messages.success(request, "Package created successfully!")
            return redirect('vendor_dashboard')
    else:
        form = TravelPackageForm()
    return render(request, 'main/create_package.html', {'form': form})

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
        edit_option = PackageDayOption.objects.filter(package_day__package=package, pk=edit_option_id).select_related('package_day').first()

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

    context = {
        'package': package,
        'package_days': package_days,
        'day_form': day_form,
        'option_form': option_form,
        'editing_day': edit_day,
        'editing_option': edit_option,
    }
    return render(request, 'main/manage_itinerary.html', context)

# ==========================================
# 5. ADMIN VIEWS
# ==========================================
@login_required
@role_required(allowed_roles=['admin'])
def admin_dashboard(request):
    # Statistics
    total_users = User.objects.count()
    total_vendors = Vendor.objects.count()
    total_packages = TravelPackage.objects.count()
    total_bookings = Booking.objects.count()

    # Recent Activity
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_packages = TravelPackage.objects.order_by('-created_at')[:5]

    context = {
        'total_users': total_users,
        'total_vendors': total_vendors,
        'total_packages': total_packages,
        'total_bookings': total_bookings,
        'recent_users': recent_users,
        'recent_packages': recent_packages,
    }
    return render(request, 'main/admin_dashboard.html', context)

@login_required
@role_required(allowed_roles=['admin'])
def manage_users(request):
    users = User.objects.filter(is_superuser=False).order_by('-date_joined')
    return render(request, 'main/manage_users.html', {'users': users})

@login_required
@role_required(allowed_roles=['admin'])
def delete_user(request, user_id):
    if request.method == 'POST':
        user_to_delete = get_object_or_404(User, id=user_id)
        if not user_to_delete.is_superuser:
            user_to_delete.delete()
            messages.success(request, f"User {user_to_delete.username} has been deleted.")
        else:
            messages.error(request, "Superusers cannot be deleted.")
    return redirect('manage_users')

@login_required
@role_required(allowed_roles=['admin'])
def manage_vendors(request):
    vendors = Vendor.objects.all().select_related('user_profile__user').order_by('name')
    return render(request, 'main/manage_vendors.html', {'vendors': vendors})

@login_required
@role_required(allowed_roles=['admin'])
def update_vendor_status(request, vendor_id, new_status):
    if request.method == 'POST':
        vendor = get_object_or_404(Vendor, id=vendor_id)
        if new_status in ['approved', 'rejected', 'pending']:
            vendor.status = new_status
            vendor.save()
            if new_status == 'approved':
                user = vendor.user_profile.user
                if not user.is_active:
                    user.is_active = True
                    user.save(update_fields=['is_active'])
            messages.success(request, f"Vendor {vendor.name} has been {new_status}.")
        else:
            messages.error(request, "Invalid status.")
    return redirect('manage_vendors')


# ==========================================
# 6. PAYMENT VIEWS
# ==========================================

@login_required
def esewa_checkout(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    transaction_uuid = str(uuid.uuid4())
    amount = Decimal(package.price).quantize(Decimal('0.01'))
    tax_amount = Decimal('0.00')
    total_amount = amount + tax_amount

    _store_pending_payment_session(
        request,
        package_id=package.id,
        transaction_uuid=transaction_uuid,
        provider='esewa',
    )

    context = {
        **_build_payment_context(package=package),
        'amount': f"{amount:.2f}",
        'tax_amount': f"{tax_amount:.2f}",
        'total_amount': f"{total_amount:.2f}",
        'transaction_uuid': transaction_uuid,
        'product_code': settings.ESEWA_PRODUCT_CODE,
        'signature': _generate_esewa_signature(
            f"{total_amount:.2f}",
            transaction_uuid,
            settings.ESEWA_PRODUCT_CODE,
        ),
        'success_url': request.build_absolute_uri(reverse('esewa_verify')),
        'failure_url': request.build_absolute_uri(reverse('payment_cancelled')),
        'esewa_form_url': settings.ESEWA_FORM_URL,
    }
    return render(request, 'main/esewa_checkout.html', context)


@login_required
@role_required(allowed_roles=['vendor'])
def esewa_sponsorship_checkout(request, package_id):
    package = get_object_or_404(
        TravelPackage.objects.select_related('vendor'),
        pk=package_id,
        vendor=_get_vendor_or_403(request),
    )
    transaction_uuid = str(uuid.uuid4())
    amount = _get_sponsorship_price(package).quantize(Decimal('0.01'))
    tax_amount = Decimal('0.00')
    total_amount = amount + tax_amount

    _store_pending_payment_session(
        request,
        sponsorship_package_id=package.id,
        transaction_uuid=transaction_uuid,
        provider='esewa',
    )

    context = {
        **_build_sponsorship_payment_context(package),
        'amount': f"{amount:.2f}",
        'tax_amount': f"{tax_amount:.2f}",
        'total_amount': f"{total_amount:.2f}",
        'transaction_uuid': transaction_uuid,
        'product_code': settings.ESEWA_PRODUCT_CODE,
        'signature': _generate_esewa_signature(
            f"{total_amount:.2f}",
            transaction_uuid,
            settings.ESEWA_PRODUCT_CODE,
        ),
        'success_url': request.build_absolute_uri(reverse('esewa_verify')),
        'failure_url': request.build_absolute_uri(reverse('payment_cancelled')),
        'esewa_form_url': settings.ESEWA_FORM_URL,
    }
    return render(request, 'main/esewa_checkout.html', context)


@login_required
def esewa_custom_itinerary_checkout(request, custom_itinerary_id):
    custom_itinerary = get_object_or_404(
        CustomItinerary.objects.select_related('package'),
        pk=custom_itinerary_id,
        user=request.user,
    )
    transaction_uuid = str(uuid.uuid4())
    amount = Decimal(custom_itinerary.final_price).quantize(Decimal('0.01'))
    tax_amount = Decimal('0.00')
    total_amount = amount + tax_amount

    _store_pending_payment_session(
        request,
        custom_itinerary_id=custom_itinerary.id,
        transaction_uuid=transaction_uuid,
        provider='esewa',
    )

    context = {
        **_build_payment_context(package=custom_itinerary.package, custom_itinerary=custom_itinerary),
        'amount': f"{amount:.2f}",
        'tax_amount': f"{tax_amount:.2f}",
        'total_amount': f"{total_amount:.2f}",
        'transaction_uuid': transaction_uuid,
        'product_code': settings.ESEWA_PRODUCT_CODE,
        'signature': _generate_esewa_signature(
            f"{total_amount:.2f}",
            transaction_uuid,
            settings.ESEWA_PRODUCT_CODE,
        ),
        'success_url': request.build_absolute_uri(reverse('esewa_verify')),
        'failure_url': request.build_absolute_uri(reverse('payment_cancelled')),
        'esewa_form_url': settings.ESEWA_FORM_URL,
    }
    return render(request, 'main/esewa_checkout.html', context)


@csrf_exempt
@login_required
def esewa_verify(request):
    data_b64 = request.GET.get('data') or request.POST.get('data')
    if not data_b64:
        messages.error(request, 'Missing eSewa verification payload.')
        return redirect('package_list')

    try:
        payload = json.loads(base64.b64decode(data_b64).decode('utf-8'))
    except Exception:
        messages.error(request, 'Invalid eSewa verification payload.')
        return redirect('package_list')

    if not _verify_esewa_payload(payload):
        return HttpResponseBadRequest('Invalid eSewa signature.')

    transaction_uuid = payload.get('transaction_uuid')
    status = payload.get('status')
    pending_transaction_uuid = request.session.get('pending_payment_transaction_uuid')

    logger.info(
        "eSewa verification callback received: status=%s transaction_uuid=%s payload=%s",
        status,
        transaction_uuid,
        payload,
    )

    if not pending_transaction_uuid or pending_transaction_uuid != transaction_uuid:
        logger.warning(
            "eSewa session mismatch: pending_transaction_uuid=%s callback_transaction_uuid=%s",
            pending_transaction_uuid,
            transaction_uuid,
        )
        return redirect(
            f"{reverse('payment_cancelled')}?reason=session_mismatch"
        )

    if status != 'COMPLETE':
        logger.warning(
            "eSewa payment not completed: status=%s transaction_uuid=%s",
            status,
            transaction_uuid,
        )
        return redirect(
            f"{reverse('payment_cancelled')}?reason=esewa_status&status={status or 'UNKNOWN'}"
        )

    if request.session.get('pending_sponsorship_package_id'):
        try:
            package = _activate_pending_sponsorship(request)
        except ValueError:
            messages.error(request, 'Could not find a pending sponsorship after eSewa verification.')
            return redirect('vendor_package_list')

        _clear_pending_payment_session(request)
        messages.success(request, f"{package.name} is now sponsored through {package.sponsorship_end}.")
        return redirect('vendor_package_list')

    try:
        booking, package, is_custom = _create_or_update_booking_from_pending_payment(request)
    except ValueError:
        messages.error(request, 'Could not find a pending booking after eSewa verification.')
        return redirect('package_list')

    _notify_booking_confirmed(booking, is_custom=is_custom)
    _clear_pending_payment_session(request)
    if is_custom:
        messages.success(request, f"Your custom booking for {package.name} is confirmed!")
    else:
        messages.success(request, f"Your booking for {package.name} is confirmed!")

    return redirect('booking_confirmation', booking_id=booking.id)

@login_required
def create_checkout_session(request, package_id):
    """
    Creates a Stripe Checkout session and redirects the user to the
    Stripe-hosted payment page.
    """
    package = get_object_or_404(TravelPackage, pk=package_id)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Define the URLs for success and cancellation
    success_url = request.build_absolute_uri(
        reverse('payment_success')
    ) + '?session_id={CHECKOUT_SESSION_ID}'
    
    cancel_url = request.build_absolute_uri(
        reverse('payment_cancelled')
    )

    try:
        # Create a new Checkout Session for the order
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': package.name,
                        'description': f"Travel Package by {package.vendor.name}",
                    },
                    # Stripe expects amount in cents
                    'unit_amount': int(package.price * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.user.email,  # Pre-fill customer email
        )

        _store_pending_payment_session(request, package_id=package.id, provider='stripe')

        return redirect(checkout_session.url, code=303)

    except Exception as e:
        messages.error(
            request,
            f"Something went wrong with the payment process. Error: {e}"
        )
        return redirect('package_detail', package_id=package.id)


@login_required
@role_required(allowed_roles=['vendor'])
def create_sponsorship_checkout_session(request, package_id):
    package = get_object_or_404(
        TravelPackage.objects.select_related('vendor'),
        pk=package_id,
        vendor=_get_vendor_or_403(request),
    )
    stripe.api_key = settings.STRIPE_SECRET_KEY

    success_url = request.build_absolute_uri(
        reverse('payment_success')
    ) + '?session_id={CHECKOUT_SESSION_ID}'

    cancel_url = request.build_absolute_uri(
        reverse('payment_cancelled')
    )

    amount = _get_sponsorship_price(package)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"{package.name} Sponsorship",
                        'description': f"Sponsored listing for {SPONSORSHIP_DURATION_DAYS} days",
                    },
                    'unit_amount': int(amount * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.user.email,
        )

        _store_pending_payment_session(
            request,
            sponsorship_package_id=package.id,
            provider='stripe',
        )

        return redirect(checkout_session.url, code=303)
    except Exception as e:
        messages.error(request, f"Something went wrong with the payment process. Error: {e}")
        return redirect('choose_sponsorship_payment', package_id=package.id)


@login_required
def create_custom_itinerary_checkout_session(request, custom_itinerary_id):
    custom_itinerary = get_object_or_404(
        CustomItinerary.objects.select_related('package', 'package__vendor'),
        pk=custom_itinerary_id,
        user=request.user,
    )
    stripe.api_key = settings.STRIPE_SECRET_KEY

    success_url = request.build_absolute_uri(
        reverse('payment_success')
    ) + '?session_id={CHECKOUT_SESSION_ID}'

    cancel_url = request.build_absolute_uri(
        reverse('payment_cancelled')
    )

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"{custom_itinerary.package.name} (Custom Itinerary)",
                        'description': f"Custom travel package by {custom_itinerary.package.vendor.name}",
                    },
                    'unit_amount': int(custom_itinerary.final_price * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.user.email,
        )

        _store_pending_payment_session(
            request,
            custom_itinerary_id=custom_itinerary.id,
            provider='stripe',
        )

        return redirect(checkout_session.url, code=303)
    except Exception as e:
        messages.error(
            request,
            f"Something went wrong with the payment process. Error: {e}"
        )
        return redirect('custom_itinerary_detail', custom_itinerary_id=custom_itinerary.id)


def payment_success(request):
    """
    Handles successful payments. Creates the booking record and shows a
    confirmation page.
    """
    if not request.session.get('pending_custom_itinerary_id') and not request.session.get('pending_booking_package_id') and not request.session.get('pending_sponsorship_package_id'):
        messages.error(request, "Could not find a pending booking. Please try again.")
        return redirect('package_list')

    if request.session.get('pending_sponsorship_package_id'):
        try:
            package = _activate_pending_sponsorship(request)
        except ValueError:
            messages.error(request, "Could not find a pending sponsorship. Please try again.")
            return redirect('vendor_package_list')

        _clear_pending_payment_session(request)
        messages.success(request, f"{package.name} is now sponsored through {package.sponsorship_end}.")
        return render(request, 'main/payment_success.html', {
            'sponsorship_package': package,
            'sponsorship_end': package.sponsorship_end,
        })

    try:
        booking, package, is_custom = _create_or_update_booking_from_pending_payment(request)
    except ValueError:
        messages.error(request, "Could not find a pending booking. Please try again.")
        return redirect('package_list')

    _notify_booking_confirmed(booking, is_custom=is_custom)
    _clear_pending_payment_session(request)

    if is_custom:
        messages.success(request, f"Your custom booking for {package.name} is confirmed!")
    else:
        messages.success(request, f"Your booking for {package.name} is confirmed!")

    return render(request, 'main/payment_success.html', {'booking': booking})


def payment_cancelled(request):
    """
    Handles cancelled payments.
    """
    reason = request.GET.get('reason', '')
    status = request.GET.get('status', '')
    sponsorship_package = None

    detail_message = "Your payment was cancelled. You have not been charged."

    if reason == 'esewa_status':
        detail_message = f"eSewa returned a non-success status: {status or 'UNKNOWN'}."
    elif reason == 'session_mismatch':
        detail_message = (
            "The payment returned from eSewa, but this app could not match it to your current checkout session."
        )

    sponsorship_package_id = request.session.get('pending_sponsorship_package_id')
    if sponsorship_package_id and request.user.is_authenticated:
        sponsorship_package = TravelPackage.objects.filter(
            pk=sponsorship_package_id,
            vendor__user=request.user,
        ).first()

    _notify_payment_cancelled(request, detail_message)
    messages.warning(request, detail_message)
    return render(
        request,
        'main/payment_cancelled.html',
        {
            'detail_message': detail_message,
            'payment_status': status,
            'cancel_reason': reason,
            'sponsorship_package': sponsorship_package,
        },
    )

@login_required
def booking_confirmation(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('package', 'package__vendor', 'custom_itinerary').prefetch_related(
            'custom_itinerary__selections__package_day',
            'custom_itinerary__selections__selected_option',
        ),
        pk=booking_id,
    )

    if booking.user != request.user:
        raise PermissionDenied

    package = booking.package
    selection_items = _build_booking_selection_items(booking.custom_itinerary)
    context = {
        'booking': booking,
        'package': package,
        'selection_items': selection_items,
        'selection_groups': _group_booking_selection_items(selection_items),
    }
    return render(request, 'main/booking_confirmation.html', context)

@login_required
@role_required(allowed_roles=['vendor'])
def export_booking_csv(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('user', 'package', 'custom_itinerary'),
        id=booking_id,
        package__vendor=_get_vendor_or_403(request)
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="booking_{booking.id}.csv"'

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

@login_required
@role_required(allowed_roles=['vendor'])
def flight_bookings(request):
    vendor = _get_vendor_or_403(request)

    bookings = Booking.objects.filter(
        package__vendor=vendor,
        custom_itinerary__selections__selected_option__option_type='flight'
    ).select_related('user', 'package').distinct()

    return render(request, 'main/flight_bookings.html', {
        'bookings': bookings
    })


def vendor_register(request):
    if request.method == 'POST':
        form = VendorRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            Vendor.objects.create(
                user=user,
                pan_card_photo=form.cleaned_data['pan_card_photo'],
                id_document_type=form.cleaned_data['id_document_type'],
                id_document_photo=form.cleaned_data['id_document_photo'],
                status='pending'
            )
            messages.info(request, "Registration submitted. Await admin approval.")
            return redirect('login')
    else:
        form = VendorRegistrationForm()
    return render(request, 'vendor/register.html', {'form': form})
