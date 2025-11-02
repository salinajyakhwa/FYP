from django.db import models
from django.contrib.auth.models import User

# Represents a user's profile, extending the built-in User model with additional information.
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # Defines the user's role, which can be 'traveler', 'vendor', or 'admin'.
    ROLE_CHOICES = (
        ('traveler', 'Traveler'),
        ('vendor', 'Vendor'),
        ('admin', 'Admin'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

# Represents a travel vendor or service provider.
class Vendor(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField()
    website = models.URLField(blank=True, null=True)
    # logo = models.ImageField(upload_to='vendor_logos/', blank=True, null=True)

    def __str__(self):
        return self.name

# Represents a travel package offered by a vendor.
class TravelPackage(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='packages')
    name = models.CharField(max_length=255)
    description = models.TextField()
    itinerary = models.JSONField(default=list)  # Changed from TextField
    price = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    # image = models.ImageField(upload_to='package_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

# Represents a booking made by a user for a travel package.
class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='bookings')
    booking_date = models.DateTimeField(auto_now_add=True)
    # Defines the status of the booking.
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    number_of_travelers = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Booking for {self.package.name} by {self.user.username}"

# Represents a review written by a user for a travel package.
class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    # Indicates whether the review is from a verified user.
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"Review for {self.package.name} by {self.user.username}"