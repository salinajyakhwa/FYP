from django.utils import timezone

from ..models import Notification, Trip
from .trips import (
    _build_trip_next_action,
    _build_trip_progress_summary,
    _build_trip_timeline_items,
)


def _build_traveler_dashboard_summary(user):
    active_trips = list(
        Trip.objects.filter(traveler=user)
        .exclude(status__in=['completed', 'cancelled', 'no_show'])
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
        .exclude(status__in=['completed', 'cancelled', 'no_show'])
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

