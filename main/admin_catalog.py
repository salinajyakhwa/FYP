from django.contrib import admin

from .models import Review, TravelPackage

admin.site.register(Review)


@admin.register(TravelPackage)
class TravelPackageAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'vendor',
        'price',
        'is_sponsored',
        'sponsorship_priority',
        'sponsorship_start',
        'sponsorship_end',
    )
    list_filter = ('is_sponsored', 'travel_type', 'location')
    search_fields = ('name', 'location', 'vendor__name')
