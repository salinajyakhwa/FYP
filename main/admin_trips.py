from django.contrib import admin

from .models import Trip, TripItem, TripItemAttachment

admin.site.register(Trip)
admin.site.register(TripItem)
admin.site.register(TripItemAttachment)
