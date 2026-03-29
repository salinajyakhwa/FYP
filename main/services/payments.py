import base64
import hashlib
import hmac
from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from ..forms import BookingTravelerForm
from ..models import Booking, CustomItinerary, PaymentLog, TravelPackage
from ..notifications import create_notification
from .access import _get_vendor_or_403, _get_vendor_user
from .itineraries import _build_action_button_label
from .trips import _create_trip_from_booking


def _quantize_currency(value):
    return Decimal(value).quantize(Decimal('0.01'))


def _get_package_unit_prices(package, custom_itinerary=None):
    adult_unit_price = Decimal(package.price)
    child_unit_price = Decimal(package.price)

    if custom_itinerary:
        adult_unit_price = Decimal(custom_itinerary.final_price)
        child_unit_price = adult_unit_price

    return {
        'adult_unit_price': _quantize_currency(adult_unit_price),
        'child_unit_price': _quantize_currency(child_unit_price),
    }


def _calculate_booking_pricing(package, adult_count, child_count, custom_itinerary=None):
    unit_prices = _get_package_unit_prices(package, custom_itinerary=custom_itinerary)
    total_travelers = adult_count + child_count
    total_price = (
        Decimal(adult_count) * unit_prices['adult_unit_price'] +
        Decimal(child_count) * unit_prices['child_unit_price']
    )

    return {
        **unit_prices,
        'adult_count': adult_count,
        'child_count': child_count,
        'total_travelers': total_travelers,
        'total_price': _quantize_currency(total_price),
    }


def _calculate_refund_amount(total_price, committed_cost):
    refund_amount = Decimal(total_price) - Decimal(committed_cost)
    return _quantize_currency(max(refund_amount, Decimal('0.00')))


def _create_payment_log(
    *,
    provider,
    payment_type,
    status,
    amount,
    user=None,
    booking=None,
    package=None,
    transaction_reference='',
    notes='',
):
    PaymentLog.objects.create(
        provider=provider,
        payment_type=payment_type,
        status=status,
        amount=_quantize_currency(amount),
        user=user,
        booking=booking,
        package=package,
        transaction_reference=transaction_reference,
        notes=notes,
    )


def _build_payment_context(*, package, custom_itinerary=None, traveler_form=None):
    traveler_form = traveler_form or BookingTravelerForm(initial={'adult_count': 1, 'child_count': 0})
    adult_count = 1
    child_count = 0

    if traveler_form.is_bound and traveler_form.is_valid():
        adult_count = traveler_form.cleaned_data['adult_count']
        child_count = traveler_form.cleaned_data['child_count']
    else:
        try:
            adult_count = max(1, int(traveler_form['adult_count'].value() or 1))
        except (TypeError, ValueError):
            adult_count = 1
        try:
            child_count = max(0, int(traveler_form['child_count'].value() or 0))
        except (TypeError, ValueError):
            child_count = 0

    pricing = _calculate_booking_pricing(
        package,
        adult_count,
        child_count,
        custom_itinerary=custom_itinerary,
    )

    return {
        'package': package,
        'custom_itinerary': custom_itinerary,
        'amount': pricing['total_price'],
        'adult_unit_price': pricing['adult_unit_price'],
        'child_unit_price': pricing['child_unit_price'],
        'adult_count': pricing['adult_count'],
        'child_count': pricing['child_count'],
        'total_travelers': pricing['total_travelers'],
        'traveler_form': traveler_form,
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


def _store_pending_payment_session(
    request,
    *,
    package_id=None,
    custom_itinerary_id=None,
    sponsorship_package_id=None,
    transaction_uuid=None,
    provider=None,
    adult_count=None,
    child_count=None,
    total_price=None,
):
    request.session['pending_booking_package_id'] = package_id
    request.session['pending_custom_itinerary_id'] = custom_itinerary_id
    request.session['pending_sponsorship_package_id'] = sponsorship_package_id
    request.session['pending_payment_provider'] = provider
    request.session['pending_payment_transaction_uuid'] = transaction_uuid
    request.session['pending_booking_adult_count'] = adult_count
    request.session['pending_booking_child_count'] = child_count
    request.session['pending_booking_total_price'] = str(total_price) if total_price is not None else None


def _clear_pending_payment_session(request):
    for key in [
        'pending_booking_package_id',
        'pending_custom_itinerary_id',
        'pending_sponsorship_package_id',
        'pending_payment_provider',
        'pending_payment_transaction_uuid',
        'pending_booking_adult_count',
        'pending_booking_child_count',
        'pending_booking_total_price',
    ]:
        request.session.pop(key, None)


def _create_or_update_booking_from_pending_payment(request):
    custom_itinerary_id = request.session.get('pending_custom_itinerary_id')
    package_id = request.session.get('pending_booking_package_id')
    adult_count = int(request.session.get('pending_booking_adult_count') or 1)
    child_count = int(request.session.get('pending_booking_child_count') or 0)

    if not custom_itinerary_id and not package_id:
        raise ValueError('No pending payment target found.')

    if custom_itinerary_id:
        custom_itinerary = get_object_or_404(
            CustomItinerary.objects.select_related('package'),
            pk=custom_itinerary_id,
            user=request.user,
        )
        pricing = _calculate_booking_pricing(
            custom_itinerary.package,
            adult_count,
            child_count,
            custom_itinerary=custom_itinerary,
        )
        total_price = _quantize_currency(
            request.session.get('pending_booking_total_price') or pricing['total_price']
        )

        booking, _ = Booking.objects.get_or_create(
            custom_itinerary=custom_itinerary,
            defaults={
                'user': request.user,
                'package': custom_itinerary.package,
                'adult_count': adult_count,
                'child_count': child_count,
                'number_of_travelers': pricing['total_travelers'],
                'total_price': total_price,
                'status': 'confirmed',
            }
        )
        if (
            booking.status != 'confirmed' or
            booking.total_price != total_price or
            booking.number_of_travelers != pricing['total_travelers'] or
            booking.adult_count != adult_count or
            booking.child_count != child_count
        ):
            booking.status = 'confirmed'
            booking.total_price = total_price
            booking.package = custom_itinerary.package
            booking.user = request.user
            booking.number_of_travelers = pricing['total_travelers']
            booking.adult_count = adult_count
            booking.child_count = child_count
            booking.save(update_fields=[
                'status',
                'total_price',
                'package',
                'user',
                'number_of_travelers',
                'adult_count',
                'child_count',
            ])
        if custom_itinerary.status != 'confirmed':
            custom_itinerary.status = 'confirmed'
            custom_itinerary.save(update_fields=['status', 'updated_at'])

        _create_trip_from_booking(booking)

        return booking, custom_itinerary.package, True

    package = get_object_or_404(TravelPackage, pk=package_id)
    pricing = _calculate_booking_pricing(package, adult_count, child_count)
    total_price = _quantize_currency(
        request.session.get('pending_booking_total_price') or pricing['total_price']
    )
    booking = Booking.objects.create(
        user=request.user,
        package=package,
        adult_count=adult_count,
        child_count=child_count,
        number_of_travelers=pricing['total_travelers'],
        total_price=total_price,
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
