from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ..forms import (
    BookingCancellationRequestForm,
    BookingDisputeForm,
    ChatMessageForm,
    CustomItinerarySelectionForm,
    ItineraryDayForm,
    ReviewForm,
)
from ..models import (
    Booking,
    BookingCapacityRequest,
    ChatThread,
    CustomItinerary,
    CustomItinerarySelection,
    Notification,
    Review,
    TravelPackage,
    Trip,
)
from ..notifications import mark_notification_read
from ..notifications import create_notification
from ..services.access import _get_chat_thread_for_user_or_403, _get_vendor_or_403, _safe_int
from ..services.capacity import can_proceed_with_capacity, get_package_capacity_summary
from ..services.dashboard import (
    _build_dashboard_next_actions,
    _build_dashboard_trip_cards,
    _build_traveler_dashboard_summary,
)
from ..services.itineraries import (
    _build_booking_selection_items,
    _build_selected_options_summary,
    _group_booking_selection_items,
)
from ..services.notifications import _notify_chat_message, _notify_custom_itinerary_saved
from ..services.payments import _build_payment_context
from ..services.trips import (
    _build_trip_next_action,
    _build_trip_progress_summary,
    _build_trip_recent_attachments,
    _build_trip_timeline_items,
    _build_trip_timeline_sections,
)


def _user_can_review_package(user, package):
    return Booking.objects.filter(
        user=user,
        package=package,
        status__in=['confirmed', 'trip_completed'],
        package__end_date__lt=timezone.now().date(),
    ).exists()


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


def package_detail(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    profile = getattr(request.user, 'userprofile', None) if request.user.is_authenticated else None
    profile_vendor = getattr(profile, 'vendor', None) if profile else None

    if (
        package.moderation_status != 'approved'
        and not request.user.is_superuser
        and not (
            request.user.is_authenticated
            and profile
            and profile.role == 'vendor'
            and profile_vendor
            and profile_vendor.id == package.vendor_id
        )
    ):
        raise PermissionDenied

    reviews = Review.objects.filter(package=package).order_by('-created_at')
    review_form = ReviewForm()
    itinerary_items = []
    is_vendor_owner = bool(
        request.user.is_authenticated
        and profile
        and profile.role == 'vendor'
        and profile_vendor
        and profile_vendor.id == package.vendor_id
    )
    package_days = package.package_days.prefetch_related('options').all()
    capacity_summary = get_package_capacity_summary(package)
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
        completed_booking_exists = _user_can_review_package(request.user, package)

        if completed_booking_exists:
            has_already_reviewed = Review.objects.filter(user=request.user, package=package).exists()
            if not has_already_reviewed:
                user_can_review = True

    return render(request, 'main/traveler/package_detail.html', {
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
        'capacity_summary': capacity_summary,
    })


@login_required
def start_package_booking(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id, moderation_status='approved')
    profile = getattr(request.user, 'userprofile', None)
    if not profile or profile.role != 'traveler':
        raise PermissionDenied

    adult_count = _safe_int(request.GET.get('adult_count', 1), 1, minimum=1)
    child_count = _safe_int(request.GET.get('child_count', 0), 0, minimum=0)
    child_under_seven_count = _safe_int(request.GET.get('child_under_seven_count', 0), 0, minimum=0)
    total_travelers = adult_count + child_count + child_under_seven_count

    allowed, approved_request, capacity_summary = can_proceed_with_capacity(
        traveler=request.user,
        package=package,
        adult_count=adult_count,
        child_count=child_count,
        child_under_seven_count=child_under_seven_count,
    )
    if allowed:
        payment_url = (
            f"{reverse('choose_payment', args=[package.id])}"
            f"?adult_count={adult_count}&child_count={child_count}&child_under_seven_count={child_under_seven_count}"
        )
        if approved_request:
            payment_url += f"&capacity_request_id={approved_request.id}"
        return redirect(payment_url)

    existing_request = (
        BookingCapacityRequest.objects.filter(
            traveler=request.user,
            package=package,
            adult_count=adult_count,
            child_count=child_count,
            child_under_seven_count=child_under_seven_count,
            status='pending',
        )
        .order_by('-created_at')
        .first()
    )
    if existing_request:
        return redirect('booking_capacity_request_pending', capacity_request_id=existing_request.id)

    capacity_request = BookingCapacityRequest.objects.create(
        traveler=request.user,
        package=package,
        adult_count=adult_count,
        child_count=child_count,
        child_under_seven_count=child_under_seven_count,
        number_of_travelers=total_travelers,
    )
    create_notification(
        user=package.vendor.user_profile.user,
        title='Over-capacity booking request',
        message=f"{request.user.username} requested {total_travelers} spot(s) for {package.name}, which exceeds the current package capacity.",
        notification_type='vendor_alert',
        target_url=reverse('vendor_dashboard'),
        dedupe_key=f"capacity-request:{capacity_request.id}",
    )
    return redirect('booking_capacity_request_pending', capacity_request_id=capacity_request.id)


@login_required
def booking_capacity_request_pending(request, capacity_request_id):
    capacity_request = get_object_or_404(
        BookingCapacityRequest.objects.select_related('package', 'package__vendor'),
        pk=capacity_request_id,
        traveler=request.user,
    )
    capacity_summary = get_package_capacity_summary(capacity_request.package)
    return render(
        request,
        'main/traveler/booking_capacity_request_pending.html',
        {
            'capacity_request': capacity_request,
            'capacity_summary': capacity_summary,
        },
    )


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

    return render(request, 'main/traveler/custom_itinerary_detail.html', {
        'custom_itinerary': custom_itinerary,
        'selections': custom_itinerary.selections.all(),
        'payment_context': _build_payment_context(
            package=custom_itinerary.package,
            custom_itinerary=custom_itinerary,
        ),
    })


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
        booking.has_review = Review.objects.filter(user=request.user, package=booking.package).exists()
        booking.can_leave_review = (
            booking.status in ['confirmed', 'trip_completed']
            and booking.package.end_date < timezone.now().date()
            and not booking.has_review
        )
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

    can_review = _user_can_review_package(request.user, package)

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
        messages.error(request, 'Please provide a rating and comment for your review.')

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
        defaults={'booking': None, 'custom_itinerary': None},
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

    return render(request, 'main/chat/chat_thread_list.html', {
        'threads': threads,
        'user_role': profile.role,
    })


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
    return render(request, 'main/chat/chat_thread_detail.html', {
        'thread': thread,
        'messages': messages_qs,
        'form': form,
        'counterpart_name': counterpart_name,
    })
