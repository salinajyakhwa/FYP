from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .models import TravelPackage, Booking, Review
from .forms import ReviewForm
from .decorators import role_required

def package_list(request):
    packages = TravelPackage.objects.all()
    return render(request, 'main/package_list.html', {'packages': packages})

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

@login_required
@role_required(allowed_roles=['vendor'])
def vendor_dashboard(request):
    # Assuming the related name from UserProfile to Vendor is 'vendor'
    vendor = request.user.userprofile.vendor
    packages = TravelPackage.objects.filter(vendor=vendor)
    context = {
        'packages': packages
    }
    return render(request, 'main/vendor_dashboard.html', context)