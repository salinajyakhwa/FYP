from django.contrib import admin

from .models import CustomItinerary, CustomItinerarySelection, PackageDay, PackageDayOption

admin.site.register(PackageDay)
admin.site.register(PackageDayOption)
admin.site.register(CustomItinerary)
admin.site.register(CustomItinerarySelection)
