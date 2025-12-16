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
    CATEGORY_CHOICES = (
        ('adventure', 'Adventure'),
        ('honeymoon', 'Honeymoon'),
        ('family', 'Family'),
        ('religious', 'Religious'),
        ('luxury', 'Luxury'),
    )

    vendor = models.ForeignKey('Vendor', on_delete=models.CASCADE, related_name='packages')
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, null=True)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='adventure')
    
    # Improved Location
    location = models.CharField(max_length=100) 
    country = models.CharField(max_length=100, default="Nepal") # Helps with filtering
    
    # JSON Fields
    itinerary = models.JSONField(default=list)
    inclusions = models.JSONField(default=list, help_text="e.g. ['Breakfast', 'Wifi', 'Guide']")
    exclusions = models.JSONField(default=list, blank=True)
    
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    start_date = models.DateField()
    end_date = models.DateField()
    duration_days = models.PositiveIntegerField(default=0, editable=False) # Auto-calculated
    
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # 1. Auto-calculate duration
        if self.start_date and self.end_date:
            delta = self.end_date - self.start_date
            self.duration_days = delta.days + 1 # +1 to include the start day
            
        # 2. Auto-generate slug if missing (basic version)
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(f"{self.name}-{self.vendor.id}")
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def savings_percent(self):
        if self.discount_price and self.price > self.discount_price:
            return int(((self.price - self.discount_price) / self.price) * 100)
        return 0



    # PRO TIP: Add these property methods to fix your templates
    @property
    def rating(self):
        aggregate = self.reviews.aggregate(avg=Avg('rating'))
        return round(aggregate['avg'] or 0, 1)

    @property
    def main_image(self):
        # Returns the first image or None
        img = self.images.first()
        return img.image if img else None

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