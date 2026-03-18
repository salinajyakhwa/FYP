from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseBadRequest
from django.contrib.auth import login, update_session_auth_hash
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
import uuid
from django.contrib.auth import get_user_model # Replaced direct User import
import stripe
from django.conf import settings
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt


# Models
from .models import (
    TravelPackage,
    PackageDay,
    PackageDayOption,
    CustomItinerary,
    CustomItinerarySelection,
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
    ChatMessageForm,
    TravelPackageForm, 
    UserUpdateForm, 
    UserProfileUpdateForm,
    PasswordChangeForm,
    CustomUserCreationForm # Ensure this is in your forms.py
)

# Decorators
from .decorators import role_required

# ==========================================
# 1. PUBLIC VIEWS (Landing, About, Listings)
# ==========================================

# New view for the root URL to handle redirection
def root_redirect_view(request):
    if request.user.is_authenticated:
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
    # Fetch top 4 packages
    packages = TravelPackage.objects.all().order_by('-created_at')[:4]
    
    # OLD: return render(request, 'home.html', {'packages': packages})
    # NEW: Add 'main/' prefix
    return render(request, 'main/home.html', {'packages': packages})

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


def _build_payment_context(*, package, custom_itinerary=None):
    amount = custom_itinerary.final_price if custom_itinerary else package.price
    return {
        'package': package,
        'custom_itinerary': custom_itinerary,
        'amount': amount,
        'display_name': f"{package.name} (Custom Itinerary)" if custom_itinerary else package.name,
    }


def _store_pending_payment_session(request, *, package_id=None, custom_itinerary_id=None, transaction_uuid=None, provider=None):
    request.session['pending_booking_package_id'] = package_id
    request.session['pending_custom_itinerary_id'] = custom_itinerary_id
    request.session['pending_payment_provider'] = provider
    request.session['pending_payment_transaction_uuid'] = transaction_uuid


def _clear_pending_payment_session(request):
    for key in [
        'pending_booking_package_id',
        'pending_custom_itinerary_id',
        'pending_payment_provider',
        'pending_payment_transaction_uuid',
    ]:
        request.session.pop(key, None)


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

        return booking, custom_itinerary.package, True

    package = get_object_or_404(TravelPackage, pk=package_id)
    booking = Booking.objects.create(
        user=request.user,
        package=package,
        number_of_travelers=1,
        total_price=package.price,
        status='confirmed'
    )
    return booking, package, False


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
    packages_list = TravelPackage.objects.all().order_by('-created_at')
    package_filter = TravelPackageFilter(request.GET, queryset=packages_list)
    
    paginator = Paginator(package_filter.qs, 9) # Show 9 packages per page
    page_number = request.GET.get('page')
    packages = paginator.get_page(page_number)

    context = {
        'packages': packages,
        'filter': package_filter
    }
    return render(request, 'main/package_list.html', context)

def package_detail(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    reviews = Review.objects.filter(package=package).order_by('-created_at')
    review_form = ReviewForm()
    itinerary_items = []
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

def compare_packages(request):
    if request.method == 'POST':
        package_ids = request.POST.getlist('package_ids')

        if len(package_ids) < 2:
            messages.warning(request, "Select at least two packages to compare.")
            return redirect('package_list')

        packages = TravelPackage.objects.filter(id__in=package_ids)
        return render(request, 'main/compare_packages.html', {'packages': packages})

    return redirect('package_list')

# ==========================================
# 2. AUTHENTICATION
# ==========================================

def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save() # user is now inactive
            profile = user.userprofile # Get the user profile
            send_verification_email(request, user, profile) # Send verification email
            messages.success(request, f"Please confirm your email address to complete the registration. Check your inbox at {user.email}.")
            return redirect('check_email') # Redirect to a page informing user to check email
    else:
        form = CustomUserCreationForm()
    return render(request, 'main/register.html', {'form': form})

# ==========================================
# 3. PRIVATE USER VIEWS (Dashboard, Profile)
# ==========================================

@login_required
def dashboard(request):
    # Redirect vendors to vendor dashboard
    if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'vendor':
        return redirect('vendor_dashboard')

    recent_bookings = Booking.objects.filter(user=request.user).order_by('-booking_date')[:5]
    
    # Booking statistics
    booking_stats = Booking.objects.filter(user=request.user).aggregate(
        total_bookings=Count('id'),
        pending_bookings=Count('id', filter=Q(status='pending')),
        confirmed_bookings=Count('id', filter=Q(status='confirmed')),
        cancelled_bookings=Count('id', filter=Q(status='cancelled'))
    )

    # Fetch packages to display on the dashboard
    packages = TravelPackage.objects.all()

    context = {
        'recent_bookings': recent_bookings,
        'booking_stats': booking_stats,
        'packages': packages, # <-- Add packages to the context
    }
    return render(request, 'main/home.html', context) 

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
    bookings = Booking.objects.filter(user=request.user).select_related('package').order_by('-booking_date')
    return render(request, 'main/my_bookings.html', {'bookings': bookings})



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
    # Get all bookings for packages owned by the vendor
    bookings = Booking.objects.filter(package__vendor=vendor).select_related('package', 'user').order_by('-booking_date')
    
    context = {
        'bookings': bookings
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

    if not pending_transaction_uuid or pending_transaction_uuid != transaction_uuid:
        messages.error(request, 'Could not match the eSewa payment to a pending checkout.')
        return redirect('package_list')

    if status != 'COMPLETE':
        messages.error(request, f'eSewa payment did not complete successfully. Status: {status}')
        return redirect('payment_cancelled')

    try:
        booking, package, is_custom = _create_or_update_booking_from_pending_payment(request)
    except ValueError:
        messages.error(request, 'Could not find a pending booking after eSewa verification.')
        return redirect('package_list')

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
    if not request.session.get('pending_custom_itinerary_id') and not request.session.get('pending_booking_package_id'):
        messages.error(request, "Could not find a pending booking. Please try again.")
        return redirect('package_list')

    try:
        booking, package, is_custom = _create_or_update_booking_from_pending_payment(request)
    except ValueError:
        messages.error(request, "Could not find a pending booking. Please try again.")
        return redirect('package_list')

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
    messages.warning(
        request,
        "Your payment was cancelled. You have not been charged."
    )
    return render(request, 'main/payment_cancelled.html')

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
    context = {
        'booking': booking,
        'package': package,
    }
    return render(request, 'main/booking_confirmation.html', context)
