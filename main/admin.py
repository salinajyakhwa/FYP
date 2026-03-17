from django.contrib import admin
from .models import (
    UserProfile,
    Vendor,
    TravelPackage,
    PackageDay,
    PackageDayOption,
    CustomItinerary,
    CustomItinerarySelection,
    Booking,
    Review,
)

admin.site.register(UserProfile)
admin.site.register(Vendor)
admin.site.register(TravelPackage)
admin.site.register(PackageDay)
admin.site.register(PackageDayOption)
admin.site.register(CustomItinerary)
admin.site.register(CustomItinerarySelection)
admin.site.register(Booking)
admin.site.register(Review)
