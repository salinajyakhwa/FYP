from django.contrib import admin

from .models import UserProfile, Vendor

admin.site.register(UserProfile)
admin.site.register(Vendor)
