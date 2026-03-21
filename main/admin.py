from django.contrib import admin
from .models import (
    UserProfile,
    Vendor,
    TravelPackage,
    PackageDay,
    PackageDayOption,
    CustomItinerary,
    CustomItinerarySelection,
    ChatThread,
    ChatMessage,
    Booking,
    Trip,
    TripItem,
    Review,
)

admin.site.register(UserProfile)
admin.site.register(Vendor)
admin.site.register(TravelPackage)
admin.site.register(PackageDay)
admin.site.register(PackageDayOption)
admin.site.register(CustomItinerary)
admin.site.register(CustomItinerarySelection)
admin.site.register(ChatThread)
admin.site.register(ChatMessage)
admin.site.register(Booking)
admin.site.register(Trip)
admin.site.register(TripItem)
admin.site.register(Review)
