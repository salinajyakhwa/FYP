from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime

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
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', default='profile_pics/default.jpg', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=100, blank=True, null=True)
    token_created_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

# Represents a travel vendor or service provider.
class Vendor(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField()
    website = models.URLField(blank=True, null=True)
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return self.name

# Represents a travel package offered by a vendor.
class TravelPackage(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='packages')
    name = models.CharField(max_length=255)
    description = models.TextField()
    location = models.CharField(max_length=255)
    travel_type = models.CharField(max_length=255)
    image = models.ImageField(upload_to='packages/', blank=True, null=True)
    itinerary = models.JSONField(default=list)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class PackageDay(models.Model):
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='package_days')
    day_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['day_number', 'sort_order', 'id']
        unique_together = [('package', 'day_number')]

    def __str__(self):
        return f"{self.package.name} - Day {self.day_number}"


class PackageDayOption(models.Model):
    OPTION_TYPE_CHOICES = (
        ('flight', 'Flight'),
        ('road', 'Road'),
        ('rail', 'Rail'),
        ('water', 'Water'),
        ('stay', 'Stay'),
        ('activity', 'Activity'),
        ('other', 'Other'),
    )

    package_day = models.ForeignKey(PackageDay, on_delete=models.CASCADE, related_name='options')
    option_type = models.CharField(max_length=20, choices=OPTION_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    additional_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_required = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    action_link = models.URLField(blank=True, null=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.package_day} - {self.title}"


class CustomItinerary(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='custom_itineraries')
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='custom_itineraries')
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Custom itinerary for {self.package.name} by {self.user.username}"


class CustomItinerarySelection(models.Model):
    custom_itinerary = models.ForeignKey(CustomItinerary, on_delete=models.CASCADE, related_name='selections')
    package_day = models.ForeignKey(PackageDay, on_delete=models.CASCADE, related_name='custom_selections')
    selected_option = models.ForeignKey(PackageDayOption, on_delete=models.CASCADE, related_name='selected_in_itineraries')
    selected_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['package_day__day_number', 'id']
        unique_together = [('custom_itinerary', 'package_day')]

    def __str__(self):
        return f"{self.custom_itinerary} - Day {self.package_day.day_number}"


class ChatThread(models.Model):
    traveler = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_threads')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='chat_threads')
    package = models.ForeignKey(
        TravelPackage,
        on_delete=models.CASCADE,
        related_name='chat_threads',
        blank=True,
        null=True,
    )
    booking = models.ForeignKey(
        'Booking',
        on_delete=models.SET_NULL,
        related_name='chat_threads',
        blank=True,
        null=True,
    )
    custom_itinerary = models.ForeignKey(
        CustomItinerary,
        on_delete=models.SET_NULL,
        related_name='chat_threads',
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['traveler', 'vendor', 'package'],
                name='unique_chat_thread_per_traveler_vendor_package',
            ),
        ]

    def __str__(self):
        if self.package:
            return f"Chat: {self.traveler.username} and {self.vendor.name} about {self.package.name}"
        return f"Chat: {self.traveler.username} and {self.vendor.name}"


class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"Message in thread {self.thread_id} by {self.sender.username}"


class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = (
        ('booking_created', 'Booking Created'),
        ('payment_success', 'Payment Success'),
        ('payment_cancelled', 'Payment Cancelled'),
        ('chat_message', 'Chat Message'),
        ('custom_itinerary_saved', 'Custom Itinerary Saved'),
        ('trip_update', 'Trip Update'),
        ('vendor_alert', 'Vendor Alert'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    target_url = models.CharField(max_length=500, blank=True)
    related_booking = models.ForeignKey('Booking', on_delete=models.SET_NULL, related_name='notifications', blank=True, null=True)
    related_custom_itinerary = models.ForeignKey(CustomItinerary, on_delete=models.SET_NULL, related_name='notifications', blank=True, null=True)
    related_thread = models.ForeignKey(ChatThread, on_delete=models.SET_NULL, related_name='notifications', blank=True, null=True)
    related_trip = models.ForeignKey('Trip', on_delete=models.SET_NULL, related_name='notifications', blank=True, null=True)
    dedupe_key = models.CharField(max_length=255, blank=True, null=True, unique=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.title}"

# Represents a booking made by a user for a travel package.
class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='bookings')
    custom_itinerary = models.OneToOneField(
        CustomItinerary,
        on_delete=models.SET_NULL,
        related_name='booking',
        blank=True,
        null=True,
    )
    booking_date = models.DateTimeField(auto_now_add=True)
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


class Trip(models.Model):
    STATUS_CHOICES = (
        ('planned', 'Planned'),
        ('ready', 'Ready'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='trip')
    traveler = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='trips')
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='trips')
    custom_itinerary = models.ForeignKey(
        CustomItinerary,
        on_delete=models.SET_NULL,
        related_name='trips',
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"Trip for booking #{self.booking_id}"


class TripItem(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('ready', 'Ready'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('blocked', 'Blocked'),
        ('cancelled', 'Cancelled'),
    )

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='items')
    package_day = models.ForeignKey(
        PackageDay,
        on_delete=models.SET_NULL,
        related_name='trip_items',
        blank=True,
        null=True,
    )
    selected_option = models.ForeignKey(
        PackageDayOption,
        on_delete=models.SET_NULL,
        related_name='trip_items',
        blank=True,
        null=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    day_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sort_order = models.PositiveIntegerField(default=0)
    action_link = models.URLField(blank=True, null=True)
    action_label = models.CharField(max_length=100, blank=True)
    vendor_notes = models.TextField(blank=True)
    traveler_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['day_number', 'sort_order', 'id']

    def __str__(self):
        return f"Trip #{self.trip_id} - Day {self.day_number}: {self.title}"


class TripItemAttachment(models.Model):
    ATTACHMENT_TYPE_CHOICES = (
        ('ticket', 'Ticket'),
        ('voucher', 'Voucher'),
        ('document', 'Document'),
        ('receipt', 'Receipt'),
        ('image', 'Image'),
        ('qr', 'QR Code'),
        ('other', 'Other'),
    )

    trip_item = models.ForeignKey(TripItem, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='trip_attachments/')
    attachment_type = models.CharField(max_length=20, choices=ATTACHMENT_TYPE_CHOICES, default='document')
    title = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_trip_attachments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"{self.trip_item} - {self.title}"

# Represents a review written by a user for a travel package.
class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"Review for {self.package.name} by {self.user.username}"

# Represents an image for a travel package. (Dummy model for migration cleanup)
class PackageImage(models.Model):
    package = models.ForeignKey(TravelPackage, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='packages/gallery/', blank=True, null=True)

    class Meta:
        app_label = 'main' # Explicitly set app_label

class Vehicle(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    capacity = models.PositiveIntegerField()
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='vehicles')
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.name

class EmailVerification(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='email_verification')
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.created_at + datetime.timedelta(days=1)
    
class EmailOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_valid(self):
        return timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.email} - {self.otp}"