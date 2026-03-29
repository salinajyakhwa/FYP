from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import CustomItinerarySelectionForm, ItineraryDayForm, ReviewForm
from .models import Booking, CustomItinerary, CustomItinerarySelection, Review, TravelPackage


def package_detail(request, package_id):
    from .views import _build_selected_options_summary, _notify_custom_itinerary_saved

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

    return render(request, 'main/package_detail.html', {
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
    })


@login_required
def custom_itinerary_detail(request, custom_itinerary_id):
    from .views import _build_payment_context

    custom_itinerary = get_object_or_404(
        CustomItinerary.objects.select_related('package', 'package__vendor', 'user').prefetch_related(
            'selections__package_day',
            'selections__selected_option',
        ),
        pk=custom_itinerary_id,
    )

    if custom_itinerary.user != request.user:
        raise PermissionDenied

    return render(request, 'main/custom_itinerary_detail.html', {
        'custom_itinerary': custom_itinerary,
        'selections': custom_itinerary.selections.all(),
        'payment_context': _build_payment_context(
            package=custom_itinerary.package,
            custom_itinerary=custom_itinerary,
        ),
    })
