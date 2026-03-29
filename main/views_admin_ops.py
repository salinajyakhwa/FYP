from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from django.contrib.auth import get_user_model

from .decorators import role_required
from .models import Booking, BookingDispute, PaymentLog, TravelPackage, Vendor
from .services.access import _sync_trip_status_from_booking
from .services.payments import _create_payment_log
from .views_vendor_ops import send_vendor_status_email

User = get_user_model()


@login_required
@role_required(allowed_roles=['admin'])
def admin_dashboard(request):
    total_users = User.objects.count()
    total_vendors = Vendor.objects.count()
    total_packages = TravelPackage.objects.count()
    total_bookings = Booking.objects.count()

    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_packages = TravelPackage.objects.order_by('-created_at')[:5]
    admin_queue = {
        'pending_vendors': Vendor.objects.filter(status='pending').count(),
        'pending_packages': TravelPackage.objects.filter(moderation_status='pending').count(),
        'open_disputes': BookingDispute.objects.filter(status__in=['open', 'reviewing']).count(),
        'refund_approvals': Booking.objects.filter(status='cancellation_reviewed').count(),
    }

    return render(request, 'main/admin/admin_dashboard.html', {
        'total_users': total_users,
        'total_vendors': total_vendors,
        'total_packages': total_packages,
        'total_bookings': total_bookings,
        'admin_queue': admin_queue,
        'recent_users': recent_users,
        'recent_packages': recent_packages,
    })


@login_required
@role_required(allowed_roles=['admin'])
def manage_users(request):
    users = User.objects.filter(is_superuser=False).order_by('-date_joined')
    return render(request, 'main/admin/manage_users.html', {'users': users})


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
    return render(request, 'main/admin/manage_vendors.html', {'vendors': vendors})


@login_required
@role_required(allowed_roles=['admin'])
def update_vendor_status(request, vendor_id, new_status):
    if request.method == 'POST':
        vendor = get_object_or_404(Vendor, id=vendor_id)
        if new_status in ['approved', 'rejected', 'pending']:
            vendor.status = new_status
            if new_status == 'rejected':
                vendor.rejection_reason = request.POST.get('rejection_reason', '').strip()
            elif new_status in ['approved', 'pending']:
                vendor.rejection_reason = ''
            vendor.save()
            if new_status == 'approved':
                user = vendor.user_profile.user
                if not user.is_active:
                    user.is_active = True
                    user.save(update_fields=['is_active'])
            if new_status in ['approved', 'rejected']:
                send_vendor_status_email(request, vendor)
            messages.success(request, f"Vendor {vendor.name} has been {new_status}.")
        else:
            messages.error(request, "Invalid status.")
    return redirect('manage_vendors')


@login_required
@role_required(allowed_roles=['admin'])
def manage_cancellation_requests(request):
    bookings = (
        Booking.objects.filter(status__in=['cancellation_requested', 'cancellation_reviewed'])
        .select_related('user', 'package', 'package__vendor')
        .order_by('-cancellation_requested_at', '-booking_date')
    )
    return render(request, 'main/admin/manage_cancellation_requests.html', {'bookings': bookings})


@login_required
@role_required(allowed_roles=['admin'])
def finalize_cancellation_request(request, booking_id, decision):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    booking = get_object_or_404(Booking, pk=booking_id)
    admin_notes = request.POST.get('admin_cancellation_notes', '').strip()

    if booking.status != 'cancellation_reviewed':
        messages.error(request, 'This booking is not ready for final cancellation approval.')
        return redirect('manage_cancellation_requests')

    if decision == 'approve':
        booking.status = 'refund_processed' if booking.refund_amount >= booking.total_price else 'partially_refunded'
        booking.admin_cancellation_notes = admin_notes
        booking.cancellation_admin_reviewed_at = timezone.now()
        booking.save(update_fields=['status', 'admin_cancellation_notes', 'cancellation_admin_reviewed_at'])
        _create_payment_log(
            provider='internal',
            payment_type='refund',
            status='refunded',
            amount=booking.refund_amount,
            user=booking.user,
            booking=booking,
            package=booking.package,
            notes='Admin approved booking cancellation refund.',
        )
        _sync_trip_status_from_booking(booking)
        messages.success(request, 'Cancellation approved and refund status recorded.')
    elif decision == 'reject':
        booking.status = 'confirmed'
        booking.admin_cancellation_notes = admin_notes
        booking.cancellation_admin_reviewed_at = timezone.now()
        booking.save(update_fields=['status', 'admin_cancellation_notes', 'cancellation_admin_reviewed_at'])
        _sync_trip_status_from_booking(booking)
        messages.success(request, 'Cancellation rejected and booking restored to confirmed.')
    else:
        messages.error(request, 'Invalid cancellation decision.')

    return redirect('manage_cancellation_requests')


@login_required
@role_required(allowed_roles=['admin'])
def manage_payment_logs(request):
    payment_logs = (
        PaymentLog.objects.select_related('user', 'booking', 'package')
        .order_by('-created_at')
    )
    return render(request, 'main/admin/manage_payment_logs.html', {'payment_logs': payment_logs})


@login_required
@role_required(allowed_roles=['admin'])
def manage_booking_disputes(request):
    disputes = (
        BookingDispute.objects.select_related('booking', 'booking__package', 'booking__package__vendor', 'opened_by')
        .order_by('-created_at')
    )
    return render(request, 'main/admin/manage_booking_disputes.html', {'disputes': disputes})


@login_required
@role_required(allowed_roles=['admin'])
def update_booking_dispute(request, dispute_id, new_status):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    dispute = get_object_or_404(BookingDispute, pk=dispute_id)
    allowed_statuses = {'reviewing', 'resolved', 'rejected'}
    if new_status not in allowed_statuses:
        messages.error(request, 'Invalid dispute status.')
        return redirect('manage_booking_disputes')

    dispute.status = new_status
    dispute.admin_notes = request.POST.get('admin_notes', '').strip()
    dispute.save(update_fields=['status', 'admin_notes', 'updated_at'])
    messages.success(request, 'Dispute updated successfully.')
    return redirect('manage_booking_disputes')


@login_required
@role_required(allowed_roles=['admin'])
def manage_package_moderation(request):
    packages = (
        TravelPackage.objects.select_related('vendor', 'vendor__user_profile', 'vendor__user_profile__user')
        .order_by('-created_at')
    )
    return render(request, 'main/admin/manage_package_moderation.html', {'packages': packages})


@login_required
@role_required(allowed_roles=['admin'])
def update_package_moderation(request, package_id, new_status):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST request required.')

    package = get_object_or_404(TravelPackage, pk=package_id)
    allowed_statuses = {'approved', 'pending', 'rejected'}
    if new_status not in allowed_statuses:
        messages.error(request, 'Invalid package moderation status.')
        return redirect('manage_package_moderation')

    package.moderation_status = new_status
    package.moderation_notes = request.POST.get('moderation_notes', '').strip()
    package.moderated_at = timezone.now()
    package.save(update_fields=['moderation_status', 'moderation_notes', 'moderated_at'])
    messages.success(request, f'{package.name} marked as {package.get_moderation_status_display()}.')
    return redirect('manage_package_moderation')
