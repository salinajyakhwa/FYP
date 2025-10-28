from django.shortcuts import render
from .models import TravelPackage

def package_list(request):
    packages = TravelPackage.objects.all()
    return render(request, 'main/package_list.html', {'packages': packages})