from django.contrib import admin
from .models import UserProfile, Vendor, TravelPackage, Booking, Review

admin.site.register(UserProfile)
admin.site.register(Vendor)
admin.site.register(TravelPackage)
admin.site.register(Booking)
admin.site.register(Review)