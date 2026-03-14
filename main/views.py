from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator # Added for pagination
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import EmailMessage
from django.utils import timezone
from django.db.models.functions import TruncMonth
import json
from django.contrib.auth import get_user_model # Replaced direct User import
import stripe
from django.conf import settings
from django.urls import reverse

# Models
from .models import TravelPackage, Booking, Review, UserProfile, Vendor

User = get_user_model() # Get the User model

# Forms
from .forms import (
    ReviewForm, 
    ItineraryFormSet, 
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
        'review_form': review_form
    }
    return render(request, 'main/package_detail.html', context)

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

    if request.method == 'POST':
        formset = ItineraryFormSet(request.POST)
        if formset.is_valid():
            # JSON Logic
            new_itinerary = []
            for form in formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    new_itinerary.append({
                        'day': form.cleaned_data.get('day'),
                        'title': form.cleaned_data.get('title'),
                        'activity_type': form.cleaned_data.get('activity_type'),
                        'description': form.cleaned_data.get('description'),
                        'inclusions': form.cleaned_data.get('inclusions'),
                    })
            package.itinerary = new_itinerary
            package.save()
            messages.success(request, "Itinerary updated!")
            return redirect('vendor_dashboard')
    else:
        initial_data = package.itinerary if isinstance(package.itinerary, list) else []
        formset = ItineraryFormSet(initial=initial_data)

    context = {
        'package': package,
        'formset': formset
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
def create_payment_options(request, package_id):
    """
    Presents payment method choices (Stripe or eSewa) for a package.
    """
    package = get_object_or_404(TravelPackage, pk=package_id)
    stripe_url = reverse('create_checkout_session', args=[package.id])
    esewa_url = reverse('create_esewa_session', args=[package.id])
    context = {
        'package': package,
        'stripe_url': stripe_url,
        'esewa_url': esewa_url,
    }
    return render(request, 'main/payment_options.html', context)

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

    # Validate user email before sending to Stripe
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError

    customer_email = None
    user_email = getattr(request.user, 'email', '') or ''
    if user_email:
        try:
            validate_email(user_email)
            customer_email = user_email
        except ValidationError:
            customer_email = None
            messages.warning(request, 'Your account email is invalid or empty; Stripe may ask for an email during payment.')

    try:
        # Create a new Checkout Session for the order
        checkout_kwargs = {
            'payment_method_types': ['card'],
            'line_items': [{
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
            'mode': 'payment',
            'success_url': success_url,
            'cancel_url': cancel_url,
        }

        if customer_email:
            checkout_kwargs['customer_email'] = customer_email

        checkout_session = stripe.checkout.Session.create(**checkout_kwargs)

        # Store package_id in session to retrieve after success
        request.session['pending_booking_package_id'] = package.id

        return redirect(checkout_session.url, code=303)

    except Exception as e:
        messages.error(
            request,
            f"Something went wrong with the payment process. Error: {e}"
        )
        return redirect('package_detail', package_id=package.id)


@login_required
def create_esewa_session(request, package_id):
    """
    Initiates an eSewa (ePay v2) payment by generating required hidden fields
    (including the HMAC signature) using django-esewa and rendering a form
    that posts to eSewa's payment URL.
    """
    package = get_object_or_404(TravelPackage, pk=package_id)

    import uuid, hmac, hashlib, base64, html

    txn_id = str(uuid.uuid4())
    success_url = request.build_absolute_uri(reverse('payment_success'))
    failure_url = request.build_absolute_uri(reverse('payment_cancelled'))

    # Prepare amounts and charges (eSewa requires tax/service/delivery fields; send 0 if unused)
    # Format amounts with two decimal places
    amount = float(package.price)
    total_amount = float(package.price)
    tax_amount = 0.0
    product_service_charge = 0.0
    product_delivery_charge = 0.0

    amount_str = f"{amount:.2f}"
    total_amount_str = f"{total_amount:.2f}"
    tax_amount_str = f"{tax_amount:.2f}"
    product_service_charge_str = f"{product_service_charge:.2f}"
    product_delivery_charge_str = f"{product_delivery_charge:.2f}"

    # Build the string to sign according to eSewa ePay v2 expectations.
    # New order includes tax/service/delivery and uses 2-decimal formatting.
    string_to_sign = (
        f"{settings.ESEWA_PRODUCT_CODE}|{amount_str}|{tax_amount_str}|{product_service_charge_str}|{product_delivery_charge_str}|{total_amount_str}|{txn_id}|{success_url}|{failure_url}"
    )

    # Compute HMAC-SHA256 and produce lowercase hex digest (some eSewa integrations expect hex)
    secret = settings.ESEWA_SECRET_KEY or ''
    digest = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha256).digest()
    signature_hex = digest.hex()

    # Build hidden input fields (escaped values)
    fields = {
        'product_code': settings.ESEWA_PRODUCT_CODE,
        'amount': amount_str,
        'total_amount': total_amount_str,
        'transaction_uuid': txn_id,
        'success_url': success_url,
        'failure_url': failure_url,
        'tax_amount': tax_amount_str,
        'product_service_charge': product_service_charge_str,
        'product_delivery_charge': product_delivery_charge_str,
        'signature': signature_hex,
    }

    form_inputs = []
    for k, v in fields.items():
        form_inputs.append(f"<input type=\"hidden\" name=\"{html.escape(k)}\" value=\"{html.escape(str(v))}\">")

    form_fields_html = "\n".join(form_inputs)

    context = {
        'form_fields': form_fields_html,
        'esewa_url': settings.ESEWA_EPAY_URL,
        'signature': signature_hex,
        'string_to_sign': string_to_sign,
        'debug_fields': form_fields_html,
    }

    # Store pending booking info to create booking after success
    request.session['pending_booking_package_id'] = package.id
    request.session['pending_payment_txn'] = txn_id

    return render(request, 'main/checkout_esewa.html', context)


def payment_success(request):
    """
    Handles successful payments from Stripe and eSewa. For eSewa, the gateway
    returns a Base64-encoded `data` GET parameter containing JSON with a
    `status` field. If status is COMPLETE, the booking is confirmed.
    """
    # eSewa returns a base64 'data' parameter
    encoded_data = request.GET.get('data')
    if encoded_data:
        import base64, json
        try:
            decoded_bytes = base64.b64decode(encoded_data)
            decoded_str = decoded_bytes.decode('utf-8')
            response_data = json.loads(decoded_str)
        except Exception:
            messages.error(request, "Invalid response from payment gateway.")
            return redirect('package_list')

        if response_data.get('status') == 'COMPLETE':
            package_id = request.session.get('pending_booking_package_id')
            if not package_id:
                messages.error(request, "Could not find a pending booking. Please contact support.")
                return redirect('package_list')

            package = get_object_or_404(TravelPackage, pk=package_id)
            Booking.objects.create(
                user=request.user,
                package=package,
                number_of_travelers=1,
                total_price=package.price,
                status='confirmed'
            )

            # Clear session variables
            request.session.pop('pending_booking_package_id', None)
            request.session.pop('pending_payment_txn', None)

            messages.success(request, f"Your booking for {package.name} is confirmed!")
            return render(request, 'main/payment_success.html', {'data': response_data})

        messages.error(request, "Payment not completed.")
        return render(request, 'main/payment_cancelled.html')

    # Fallback — existing Stripe flow that relied on session data
    package_id = request.session.get('pending_booking_package_id')

    if not package_id:
        messages.error(request, "Could not find a pending booking. Please try again.")
        return redirect('package_list')

    package = get_object_or_404(TravelPackage, pk=package_id)

    # Create booking after successful payment (Stripe)
    Booking.objects.create(
        user=request.user,
        package=package,
        number_of_travelers=1,  # You can replace with form value later
        total_price=package.price,
        status='confirmed'
    )

    # Clear session variable
    del request.session['pending_booking_package_id']

    messages.success(request, f"Your booking for {package.name} is confirmed!")

    return render(request, 'main/payment_success.html')


def payment_cancelled(request):
    """
    Handles cancelled payments.
    """
    messages.warning(
        request,
        "Your payment was cancelled. You have not been charged."
    )
    return render(request, 'main/payment_cancelled.html')
