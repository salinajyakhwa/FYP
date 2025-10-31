from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .models import TravelPackage, Booking

def package_list(request):
    packages = TravelPackage.objects.all()
    return render(request, 'main/package_list.html', {'packages': packages})

def package_detail(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    return render(request, 'main/package_detail.html', {'package': package})

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
def book_package(request, package_id):
    package = get_object_or_404(TravelPackage, pk=package_id)
    # For simplicity, we assume 1 traveler for now.
    booking = Booking.objects.create(
        user=request.user,
        package=package,
        number_of_travelers=1,
        total_price=package.price
    )
    # We will create the my_bookings page next
    return redirect('package_list') # Temporary redirect