from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import TravelPackage, Booking, Review
from .forms import ReviewForm, ItineraryFormSet, TravelPackageForm, UserUpdateForm, PasswordChangeForm
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash

@login_required
def profile(request):
    if request.method == 'POST':
        # Distinguish between the two forms
        if 'update_profile' in request.POST:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            if user_form.is_valid():
                user_form.save()
                messages.success(request, 'Your profile has been updated successfully!')
                return redirect('profile')
        
        elif 'change_password' in request.POST:
            pass_form = PasswordChangeForm(request.user, request.POST)
            if pass_form.is_valid():
                user = pass_form.save()
                update_session_auth_hash(request, user)  # Important!
                messages.success(request, 'Your password was successfully updated!')
                return redirect('profile')
            else:
                messages.error(request, 'Please correct the error below.')

    user_form = UserUpdateForm(instance=request.user)
    pass_form = PasswordChangeForm(request.user)

    context = {
        'user_form': user_form,
        'pass_form': pass_form
    }
    return render(request, 'main/profile.html', context)

@login_required
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)

    # Check if the user owns this booking
    if booking.user != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        # Only allow cancellation if the booking is pending or confirmed
        if booking.status in ['pending', 'confirmed']:
            booking.status = 'cancelled'
            booking.save()
            messages.success(request, f'Your booking for "{booking.package.name}" has been cancelled.')
        else:
            messages.error(request, 'This booking cannot be cancelled.')
    
    return redirect('my_bookings')

from .decorators import role_required

from django.db.models import Q

# --- Public Views ---

def package_list(request):
    query = request.GET.get('q')
    if query:
        packages = TravelPackage.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
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
        if Booking.objects.filter(user=request.user, package=package, status='confirmed').exists():
            user_can_review = True
    context = {
        'package': package,
        'reviews': reviews,
        'user_can_review': user_can_review,
        'review_form': review_form
    }
    return render(request, 'main/package_detail.html', context)

# --- Authentication Views ---

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('package_list')
    else:
        form = UserCreationForm()
    return render(request, 'main/register.html', {'form': form})

# --- User-specific Views ---

@login_required
def add_review(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.package = package
            review.user = request.user
            review.is_verified = True
            review.save()
            return redirect('package_detail', package_id=package.id)
    return redirect('package_detail', package_id=package.id)

@login_required
def book_package(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    booking = Booking.objects.create(
        user=request.user,
        package=package,
        number_of_travelers=1,
        total_price=package.price
    )
    return redirect('my_bookings')

@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).order_by('-booking_date')
    return render(request, 'main/my_bookings.html', {'bookings': bookings})

# --- Vendor Views ---

@login_required
@role_required(allowed_roles=['vendor'])
def vendor_dashboard(request):
    vendor = request.user.userprofile.vendor
    packages = TravelPackage.objects.filter(vendor=vendor)
    context = {
        'packages': packages
    }
    return render(request, 'main/vendor_dashboard.html', context)

def compare_packages(request):
    if request.method == 'POST':
        package_ids = request.POST.getlist('package_ids')
        if len(package_ids) < 2:
            # Handle error: not enough packages to compare
            return redirect('package_list') # Or render with an error message
        
        packages = TravelPackage.objects.filter(id__in=package_ids)
        return render(request, 'main/compare_packages.html', {'packages': packages})
    
    return redirect('package_list')

@login_required
@role_required(allowed_roles=['vendor'])
def create_package(request):
    if request.method == 'POST':
        form = TravelPackageForm(request.POST)
        if form.is_valid():
            package = form.save(commit=False)
            package.vendor = request.user.userprofile.vendor
            package.save()
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
            new_itinerary = []
            for form in formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    new_itinerary.append({
                        'day': form.cleaned_data['day'],
                        'title': form.cleaned_data['title'],
                        'description': form.cleaned_data['description'],
                    })
            package.itinerary = new_itinerary
            package.save()
            return redirect('vendor_dashboard')
    else:
        initial_data = package.itinerary if isinstance(package.itinerary, list) else []
        formset = ItineraryFormSet(initial=initial_data)

    context = {
        'package': package,
        'formset': formset
    }
    return render(request, 'main/manage_itinerary.html', context)