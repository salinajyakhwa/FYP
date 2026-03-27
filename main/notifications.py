from django.utils import timezone

from .models import Notification


def create_notification(
    *,
    user,
    title,
    message,
    notification_type,
    target_url='',
    related_booking=None,
    related_custom_itinerary=None,
    related_thread=None,
    related_trip=None,
    dedupe_key=None,
):
    payload = {
        'title': title,
        'message': message,
        'notification_type': notification_type,
        'target_url': target_url or '',
        'related_booking': related_booking,
        'related_custom_itinerary': related_custom_itinerary,
        'related_thread': related_thread,
        'related_trip': related_trip,
    }

    if dedupe_key:
        notification, created = Notification.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={'user': user, **payload},
        )
        if not created and notification.user_id == user.id:
            for field, value in payload.items():
                setattr(notification, field, value)
            notification.is_read = False
            notification.read_at = None
            notification.save()
        return notification

    return Notification.objects.create(user=user, **payload)


def mark_notification_read(notification):
    if notification.is_read:
        return notification
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=['is_read', 'read_at'])
    return notification
