from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator # Added for pagination

# Models
from .models import TravelPackage, Booking, Review

# Forms
from .forms import (
    ReviewForm, 
    ItineraryFormSet, 
    TravelPackageForm, 
    UserUpdateForm, 
    PasswordChangeForm,
    CustomUserCreationForm # Ensure this is in your forms.py
)

# Decorators
from .decorators import role_required

# ==========================================
# 1. PUBLIC VIEWS (Landing, About, Listings)
# ==========================================

def home(request):
    # Fetch top 4 packages
    packages = TravelPackage.objects.prefetch_related('images').all().order_by('-created_at')[:4]
    
    # OLD: return render(request, 'home.html', {'packages': packages})
    # NEW: Add 'main/' prefix
    return render(request, 'main/home.html', {'packages': packages})

@login_required
def dashboard(request):
    # Redirect vendors
    if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'vendor':
        return redirect('vendor_dashboard')
    
    # Regular users go to their bookings
    return redirect('my_bookings')

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

def package_list(request):
    query = request.GET.get('q')
    if query:
        packages = TravelPackage.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(vendor__name__icontains=query)
        )
    else:
        packages = TravelPackage.objects.all()
    return render(request, 'main/package_list.html', {'packages': packages, 'query': query})

def package_detail(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    reviews = Review.objects.filter(package=package).order_by('-created_at')
    review_form = ReviewForm()
    
    user_can_review = False
    if request.user.is_authenticated:
        # Check if user has a confirmed booking AND has not already reviewed
        has_confirmed_booking = Booking.objects.filter(user=request.user, package=package, status='confirmed').exists()
        has_already_reviewed = Review.objects.filter(user=request.user, package=package).exists()
        if has_confirmed_booking and not has_already_reviewed:
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
        return redirect('home')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # UserProfile creation is handled via signals (best practice) or form save
            login(request, user)
            messages.success(request, f"Welcome, {user.username}!")
            return redirect('home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'main/register.html', {'form': form})

# ==========================================
# 3. PRIVATE USER VIEWS (Dashboard, Profile)
# ==========================================

@login_required
def dashboard(request):
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
    if request.method == 'POST':
        if 'update_profile' in request.POST:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            if user_form.is_valid():
                user_form.save()
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
        pass_form = PasswordChangeForm(request.user)

    context = {
        'user_form': user_form,
        'pass_form': pass_form
    }
    return render(request, 'main/profile.html', context)

@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).select_related('package').order_by('-booking_date')
    return render(request, 'main/my_bookings.html', {'bookings': bookings})

@login_required
def book_package(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    
    # Logic to prevent double booking if needed
    # ...

    Booking.objects.create(
        user=request.user,
        package=package,
        number_of_travelers=1, # Default to 1, ideally should come from a form
        total_price=package.price
    )
    messages.success(request, f"Successfully booked {package.name}!")
    return redirect('my_bookings')

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

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.package = package
            review.user = request.user
            review.is_verified = True # Assuming booking implies verification
            review.save()
            messages.success(request, 'Thank you for your review!')
            return redirect('package_detail', package_id=package.id)
            
    # Redirect if not a POST request or form is invalid
    return redirect('package_detail', package_id=package.id)

# ==========================================
# 4. VENDOR VIEWS
# ==========================================

@login_required
@role_required(allowed_roles=['vendor'])
def vendor_dashboard(request):
    vendor_profile = request.user.userprofile.vendor # Assumes OneToOne link
    packages = TravelPackage.objects.filter(vendor=vendor_profile)

    # Stats
    total_packages = packages.count()
    vendor_bookings = Booking.objects.filter(package__vendor=vendor_profile)
    total_bookings = vendor_bookings.count()
    pending_bookings = vendor_bookings.filter(status='pending').count()
    
    # Calculate Revenue (Simple aggregation)
    total_revenue = sum(b.total_price for b in vendor_bookings if b.status == 'confirmed')

    context = {
        'packages': packages,
        'total_packages': total_packages,
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'total_revenue': total_revenue
    }
    return render(request, 'main/vendor_dashboard.html', context)

@login_required
@role_required(allowed_roles=['vendor'])
def create_package(request):
    if request.method == 'POST':
        form = TravelPackageForm(request.POST, request.FILES) # Added request.FILES for images
        if form.is_valid():
            package = form.save(commit=False)
            package.vendor = request.user.userprofile.vendor
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
    
    if package.vendor != request.user.userprofile.vendor:
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
                        'description': form.cleaned_data.get('description'),
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