from django.contrib import admin
from .models import UserProfile, Vendor, TravelPackage, Booking, Review, PackageImage

class PackageImageInline(admin.TabularInline):
    model = PackageImage
    extra = 1

class TravelPackageAdmin(admin.ModelAdmin):
    inlines = [PackageImageInline]

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(Vendor)
admin.site.register(TravelPackage, TravelPackageAdmin)
admin.site.register(Booking)
admin.site.register(Review)
admin.site.register(PackageImage)