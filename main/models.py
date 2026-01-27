from django.db import models
from django.contrib.auth.models import User
from django.db.models import Avg
from datetime import date
from django.core.exceptions import ValidationError

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    ROLE_CHOICES = (
        ('traveler', 'Traveler'),
        ('vendor', 'Vendor'),
        ('admin', 'Admin'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

class Vendor(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField()
    website = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name

class TravelPackage(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='packages')
    name = models.CharField(max_length=255)
    description = models.TextField()
    
    # New fields
    location = models.CharField(max_length=255, help_text="e.g., Paris, France")
    hotel_info = models.TextField(blank=True, null=True, help_text="Details about accommodation")
    
    TRAVEL_TYPE_CHOICES = [
        ('adventure', 'Adventure'),
        ('relax', 'Relaxation'),
        ('cultural', 'Cultural'),
        ('city_break', 'City Break'),
        ('beach', 'Beach'),
        ('nature', 'Nature & Wildlife'),
        ('cruise', 'Cruise'),
    ]
    travel_type = models.CharField(
        max_length=50,
        choices=TRAVEL_TYPE_CHOICES,
        default='relax',
        help_text="Category of travel"
    )

    itinerary = models.JSONField(default=list)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class PackageImage(models.Model):
    package = models.ForeignKey(TravelPackage, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='package_images/')

class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='bookings')
    booking_date = models.DateTimeField(auto_now_add=True)
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    number_of_travelers = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)