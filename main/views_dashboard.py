from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Booking, ChatThread, Notification
from .notifications import mark_notification_read
from .services.dashboard import (
    _build_dashboard_next_actions,
    _build_dashboard_trip_cards,
    _build_traveler_dashboard_summary,
)


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect('admin_dashboard')

    if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'admin':
        return redirect('admin_dashboard')

    if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'vendor':
        return redirect('vendor_dashboard')

    recent_bookings = list(
        Booking.objects.filter(user=request.user)
        .select_related('package', 'package__vendor', 'trip', 'operations')
        .order_by('-booking_date')[:1]
    )

    recent_notifications = list(
        Notification.objects.filter(user=request.user)
        .order_by('-created_at')[:3]
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

    return render(request, 'main/traveler/traveler_dashboard.html', {
        'dashboard_summary': _build_traveler_dashboard_summary(request.user),
        'active_trip_cards': _build_dashboard_trip_cards(request.user, limit=1),
        'next_actions': _build_dashboard_next_actions(request.user),
        'recent_notifications': recent_notifications,
        'recent_threads': recent_threads,
        'recent_bookings': recent_bookings,
    })


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).select_related(
        'related_booking',
        'related_custom_itinerary',
        'related_thread',
        'related_trip',
    )
    return render(request, 'main/traveler/notifications.html', {'notifications': notifications})


@login_required
def mark_notification_read_view(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    mark_notification_read(notification)
    target_url = notification.target_url or '/notifications/'
    return redirect(target_url)


@login_required
def mark_all_notifications_read(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )
    messages.success(request, 'All notifications marked as read.')
    return redirect('notification_list')
