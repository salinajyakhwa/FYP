import base64
import json
import logging
import uuid
from decimal import Decimal

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .decorators import role_required
from .forms import BookingTravelerForm
from .models import CustomItinerary, TravelPackage

logger = logging.getLogger(__name__)


@login_required
def choose_payment(request, package_id):
    from .views import _build_payment_context, _safe_int

    package = get_object_or_404(TravelPackage, pk=package_id)
    initial = {
        'adult_count': _safe_int(request.GET.get('adult_count', 1) or 1, 1, minimum=1),
        'child_count': _safe_int(request.GET.get('child_count', 0) or 0, 0, minimum=0),
    }
    traveler_form = BookingTravelerForm(initial=initial)
    return render(
        request,
        'main/choose_payment.html',
        _build_payment_context(package=package, traveler_form=traveler_form),
    )


@login_required
def choose_custom_itinerary_payment(request, custom_itinerary_id):
    from .views import _build_payment_context, _safe_int

    custom_itinerary = get_object_or_404(
        CustomItinerary.objects.select_related('package'),
        pk=custom_itinerary_id,
        user=request.user,
    )
    initial = {
        'adult_count': _safe_int(request.GET.get('adult_count', 1) or 1, 1, minimum=1),
        'child_count': _safe_int(request.GET.get('child_count', 0) or 0, 0, minimum=0),
    }
    traveler_form = BookingTravelerForm(initial=initial)
    return render(
        request,
        'main/choose_payment.html',
        _build_payment_context(
            package=custom_itinerary.package,
            custom_itinerary=custom_itinerary,
            traveler_form=traveler_form,
        ),
    )


@login_required
@role_required(allowed_roles=['vendor'])
def choose_sponsorship_payment(request, package_id):
    from .views import _build_sponsorship_payment_context, _get_vendor_or_403

    package = get_object_or_404(
        TravelPackage.objects.select_related('vendor'),
        pk=package_id,
        vendor=_get_vendor_or_403(request),
    )
    return render(request, 'main/choose_payment.html', _build_sponsorship_payment_context(package))


@login_required
def esewa_checkout(request, package_id):
    from .views import (
        _build_payment_context,
        _calculate_booking_pricing,
        _create_payment_log,
        _generate_esewa_signature,
        _store_pending_payment_session,
    )

    package = get_object_or_404(TravelPackage, pk=package_id)
    if request.method != 'POST':
        return redirect('choose_payment', package_id=package.id)

    traveler_form = BookingTravelerForm(request.POST)
    if not traveler_form.is_valid():
        return render(
            request,
            'main/choose_payment.html',
            _build_payment_context(package=package, traveler_form=traveler_form),
        )

    adult_count = traveler_form.cleaned_data['adult_count']
    child_count = traveler_form.cleaned_data['child_count']
    pricing = _calculate_booking_pricing(package, adult_count, child_count)
    transaction_uuid = str(uuid.uuid4())
    amount = pricing['total_price']
    tax_amount = Decimal('0.00')
    total_amount = amount + tax_amount

    _store_pending_payment_session(
        request,
        package_id=package.id,
        transaction_uuid=transaction_uuid,
        provider='esewa',
        adult_count=adult_count,
        child_count=child_count,
        total_price=pricing['total_price'],
    )
    _create_payment_log(
        provider='esewa',
        payment_type='booking',
        status='initiated',
        amount=pricing['total_price'],
        user=request.user,
        package=package,
        transaction_reference=transaction_uuid,
    )

    context = {
        **_build_payment_context(package=package, traveler_form=traveler_form),
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
    from .views import (
        _build_sponsorship_payment_context,
        _create_payment_log,
        _generate_esewa_signature,
        _get_sponsorship_price,
        _get_vendor_or_403,
        _store_pending_payment_session,
    )

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
    _create_payment_log(
        provider='esewa',
        payment_type='sponsorship',
        status='initiated',
        amount=amount,
        user=request.user,
        package=package,
        transaction_reference=transaction_uuid,
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
    from .views import (
        _build_payment_context,
        _calculate_booking_pricing,
        _create_payment_log,
        _generate_esewa_signature,
        _store_pending_payment_session,
    )

    custom_itinerary = get_object_or_404(
        CustomItinerary.objects.select_related('package'),
        pk=custom_itinerary_id,
        user=request.user,
    )
    if request.method != 'POST':
        return redirect('choose_custom_itinerary_payment', custom_itinerary_id=custom_itinerary.id)

    traveler_form = BookingTravelerForm(request.POST)
    if not traveler_form.is_valid():
        return render(
            request,
            'main/choose_payment.html',
            _build_payment_context(
                package=custom_itinerary.package,
                custom_itinerary=custom_itinerary,
                traveler_form=traveler_form,
            ),
        )

    adult_count = traveler_form.cleaned_data['adult_count']
    child_count = traveler_form.cleaned_data['child_count']
    pricing = _calculate_booking_pricing(
        custom_itinerary.package,
        adult_count,
        child_count,
        custom_itinerary=custom_itinerary,
    )
    transaction_uuid = str(uuid.uuid4())
    amount = pricing['total_price']
    tax_amount = Decimal('0.00')
    total_amount = amount + tax_amount

    _store_pending_payment_session(
        request,
        custom_itinerary_id=custom_itinerary.id,
        transaction_uuid=transaction_uuid,
        provider='esewa',
        adult_count=adult_count,
        child_count=child_count,
        total_price=pricing['total_price'],
    )
    _create_payment_log(
        provider='esewa',
        payment_type='custom_itinerary',
        status='initiated',
        amount=pricing['total_price'],
        user=request.user,
        package=custom_itinerary.package,
        transaction_reference=transaction_uuid,
    )

    context = {
        **_build_payment_context(
            package=custom_itinerary.package,
            custom_itinerary=custom_itinerary,
            traveler_form=traveler_form,
        ),
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
    from .views import (
        _activate_pending_sponsorship,
        _clear_pending_payment_session,
        _create_or_update_booking_from_pending_payment,
        _create_payment_log,
        _get_sponsorship_price,
        _notify_booking_confirmed,
        _verify_esewa_payload,
    )

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
        return redirect(f"{reverse('payment_cancelled')}?reason=session_mismatch")

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
        _create_payment_log(
            provider='esewa',
            payment_type='sponsorship',
            status='success',
            amount=_get_sponsorship_price(package),
            user=request.user,
            package=package,
            transaction_reference=transaction_uuid or '',
        )
        messages.success(request, f"{package.name} is now sponsored through {package.sponsorship_end}.")
        return redirect('vendor_package_list')

    try:
        booking, package, is_custom = _create_or_update_booking_from_pending_payment(request)
    except ValueError:
        messages.error(request, 'Could not find a pending booking after eSewa verification.')
        return redirect('package_list')

    _notify_booking_confirmed(booking, is_custom=is_custom)
    _clear_pending_payment_session(request)
    _create_payment_log(
        provider='esewa',
        payment_type='custom_itinerary' if is_custom else 'booking',
        status='success',
        amount=booking.total_price,
        user=request.user,
        booking=booking,
        package=package,
        transaction_reference=transaction_uuid or '',
    )
    if is_custom:
        messages.success(request, f"Your custom booking for {package.name} is confirmed!")
    else:
        messages.success(request, f"Your booking for {package.name} is confirmed!")

    return redirect('booking_confirmation', booking_id=booking.id)


@login_required
def create_checkout_session(request, package_id):
    from .views import (
        _build_payment_context,
        _calculate_booking_pricing,
        _create_payment_log,
        _store_pending_payment_session,
    )

    package = get_object_or_404(TravelPackage, pk=package_id)
    if request.method != 'POST':
        return redirect('choose_payment', package_id=package.id)

    traveler_form = BookingTravelerForm(request.POST)
    if not traveler_form.is_valid():
        return render(
            request,
            'main/choose_payment.html',
            _build_payment_context(package=package, traveler_form=traveler_form),
        )

    adult_count = traveler_form.cleaned_data['adult_count']
    child_count = traveler_form.cleaned_data['child_count']
    pricing = _calculate_booking_pricing(package, adult_count, child_count)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    success_url = request.build_absolute_uri(reverse('payment_success')) + '?session_id={CHECKOUT_SESSION_ID}'
    cancel_url = request.build_absolute_uri(reverse('payment_cancelled'))

    try:
        line_items = []
        if adult_count:
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"{package.name} - Adult Traveler",
                        'description': f"Travel Package by {package.vendor.name}",
                    },
                    'unit_amount': int(pricing['adult_unit_price'] * 100),
                },
                'quantity': adult_count,
            })
        if child_count:
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"{package.name} - Child Traveler",
                        'description': f"Travel Package by {package.vendor.name}",
                    },
                    'unit_amount': int(pricing['child_unit_price'] * 100),
                },
                'quantity': child_count,
            })
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.user.email,
        )

        _store_pending_payment_session(
            request,
            package_id=package.id,
            provider='stripe',
            adult_count=adult_count,
            child_count=child_count,
            total_price=pricing['total_price'],
        )
        _create_payment_log(
            provider='stripe',
            payment_type='booking',
            status='initiated',
            amount=pricing['total_price'],
            user=request.user,
            package=package,
            transaction_reference=checkout_session.id,
        )

        return redirect(checkout_session.url, code=303)

    except Exception as e:
        messages.error(request, f"Something went wrong with the payment process. Error: {e}")
        return redirect('package_detail', package_id=package.id)


@login_required
@role_required(allowed_roles=['vendor'])
def create_sponsorship_checkout_session(request, package_id):
    from .views import _create_payment_log, _get_sponsorship_price, _get_vendor_or_403, _store_pending_payment_session

    package = get_object_or_404(
        TravelPackage.objects.select_related('vendor'),
        pk=package_id,
        vendor=_get_vendor_or_403(request),
    )
    stripe.api_key = settings.STRIPE_SECRET_KEY

    success_url = request.build_absolute_uri(reverse('payment_success')) + '?session_id={CHECKOUT_SESSION_ID}'
    cancel_url = request.build_absolute_uri(reverse('payment_cancelled'))
    amount = _get_sponsorship_price(package)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"{package.name} Sponsorship",
                        'description': f"Sponsored listing for {settings.SPONSORSHIP_DURATION_DAYS if hasattr(settings, 'SPONSORSHIP_DURATION_DAYS') else 30} days",
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
        _create_payment_log(
            provider='stripe',
            payment_type='sponsorship',
            status='initiated',
            amount=amount,
            user=request.user,
            package=package,
            transaction_reference=checkout_session.id,
        )

        return redirect(checkout_session.url, code=303)
    except Exception as e:
        messages.error(request, f"Something went wrong with the payment process. Error: {e}")
        return redirect('choose_sponsorship_payment', package_id=package.id)


@login_required
def create_custom_itinerary_checkout_session(request, custom_itinerary_id):
    from .views import (
        _build_payment_context,
        _calculate_booking_pricing,
        _create_payment_log,
        _store_pending_payment_session,
    )

    custom_itinerary = get_object_or_404(
        CustomItinerary.objects.select_related('package', 'package__vendor'),
        pk=custom_itinerary_id,
        user=request.user,
    )
    if request.method != 'POST':
        return redirect('choose_custom_itinerary_payment', custom_itinerary_id=custom_itinerary.id)

    traveler_form = BookingTravelerForm(request.POST)
    if not traveler_form.is_valid():
        return render(
            request,
            'main/choose_payment.html',
            _build_payment_context(
                package=custom_itinerary.package,
                custom_itinerary=custom_itinerary,
                traveler_form=traveler_form,
            ),
        )

    adult_count = traveler_form.cleaned_data['adult_count']
    child_count = traveler_form.cleaned_data['child_count']
    pricing = _calculate_booking_pricing(
        custom_itinerary.package,
        adult_count,
        child_count,
        custom_itinerary=custom_itinerary,
    )
    stripe.api_key = settings.STRIPE_SECRET_KEY

    success_url = request.build_absolute_uri(reverse('payment_success')) + '?session_id={CHECKOUT_SESSION_ID}'
    cancel_url = request.build_absolute_uri(reverse('payment_cancelled'))

    try:
        line_items = []
        if adult_count:
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"{custom_itinerary.package.name} (Custom) - Adult Traveler",
                        'description': f"Custom travel package by {custom_itinerary.package.vendor.name}",
                    },
                    'unit_amount': int(pricing['adult_unit_price'] * 100),
                },
                'quantity': adult_count,
            })
        if child_count:
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"{custom_itinerary.package.name} (Custom) - Child Traveler",
                        'description': f"Custom travel package by {custom_itinerary.package.vendor.name}",
                    },
                    'unit_amount': int(pricing['child_unit_price'] * 100),
                },
                'quantity': child_count,
            })
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.user.email,
        )

        _store_pending_payment_session(
            request,
            custom_itinerary_id=custom_itinerary.id,
            provider='stripe',
            adult_count=adult_count,
            child_count=child_count,
            total_price=pricing['total_price'],
        )
        _create_payment_log(
            provider='stripe',
            payment_type='custom_itinerary',
            status='initiated',
            amount=pricing['total_price'],
            user=request.user,
            package=custom_itinerary.package,
            transaction_reference=checkout_session.id,
        )

        return redirect(checkout_session.url, code=303)
    except Exception as e:
        messages.error(request, f"Something went wrong with the payment process. Error: {e}")
        return redirect('custom_itinerary_detail', custom_itinerary_id=custom_itinerary.id)


def payment_success(request):
    from .views import (
        _activate_pending_sponsorship,
        _clear_pending_payment_session,
        _create_or_update_booking_from_pending_payment,
        _create_payment_log,
        _get_sponsorship_price,
        _notify_booking_confirmed,
    )

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
        _create_payment_log(
            provider='stripe',
            payment_type='sponsorship',
            status='success',
            amount=_get_sponsorship_price(package),
            user=request.user,
            package=package,
            transaction_reference=request.GET.get('session_id', ''),
        )
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
    _create_payment_log(
        provider='stripe',
        payment_type='custom_itinerary' if is_custom else 'booking',
        status='success',
        amount=booking.total_price,
        user=request.user,
        booking=booking,
        package=package,
        transaction_reference=request.GET.get('session_id', ''),
    )

    if is_custom:
        messages.success(request, f"Your custom booking for {package.name} is confirmed!")
    else:
        messages.success(request, f"Your booking for {package.name} is confirmed!")

    return render(request, 'main/payment_success.html', {'booking': booking})


def payment_cancelled(request):
    from .views import _create_payment_log, _notify_payment_cancelled

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
    pending_package_id = request.session.get('pending_booking_package_id') or request.session.get('pending_sponsorship_package_id')
    pending_package = TravelPackage.objects.filter(pk=pending_package_id).first() if pending_package_id else None
    payment_type = 'sponsorship' if request.session.get('pending_sponsorship_package_id') else (
        'custom_itinerary' if request.session.get('pending_custom_itinerary_id') else 'booking'
    )
    _create_payment_log(
        provider=request.session.get('pending_payment_provider') or 'unknown',
        payment_type=payment_type,
        status='cancelled',
        amount=Decimal(request.session.get('pending_booking_total_price') or '0.00'),
        user=request.user if request.user.is_authenticated else None,
        package=pending_package,
        transaction_reference=request.session.get('pending_payment_transaction_uuid', ''),
        notes=detail_message,
    )
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
