import random
from datetime import timedelta, date
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from main.models import UserProfile, Vendor, TravelPackage, Booking, Review, PackageImage

USER_COUNT = 5
PASSWORD = 'password123'

class Command(BaseCommand):
    help = 'Generates dummy data for the travel application'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("Deleting old data...")
        # Keep superusers
        # Delete in this specific order to avoid Foreign Key errors
        Review.objects.all().delete()
        Booking.objects.all().delete()
        PackageImage.objects.all().delete()  # <--- CRITICAL: Delete images before packages
        TravelPackage.objects.all().delete()
        Vendor.objects.all().delete()
        UserProfile.objects.all().delete()

        # Optionally delete users (excluding superusers)
        User.objects.filter(is_superuser=False).delete()

        self.stdout.write("Creating new data...")

        # --- Create Users and Profiles ---
        travelers = []
        vendor_users = []
        for i in range(USER_COUNT):
            # Create traveler
            traveler_user = User.objects.create_user(username=f'traveler{i+1}', password=PASSWORD, first_name=f'T{i+1}', last_name=f'User{i+1}')
            UserProfile.objects.create(user=traveler_user, role='traveler')
            travelers.append(traveler_user)

            # Create vendor user
            vendor_user = User.objects.create_user(username=f'vendor{i+1}', password=PASSWORD, first_name=f'V{i+1}', last_name=f'Owner{i+1}')
            vendor_profile = UserProfile.objects.create(user=vendor_user, role='vendor')
            vendor_users.append(vendor_profile)
        
        self.stdout.write(f"{len(travelers)} travelers and {len(vendor_users)} vendor users created.")

        # --- Create Vendors ---
        vendor_names = ['Happy Trails', 'Sunrise Tours', 'Ocean Breeze Vacations', 'Mountain Top Adventures', 'City Scape Getaways']
        vendors = []
        for i in range(USER_COUNT):
            vendor = Vendor.objects.create(
                user_profile=vendor_users[i],
                name=vendor_names[i],
                description=f'Your number one choice for {vendor_names[i]}.',
                website=f'https://www.{vendor_names[i].lower().replace(" ", "")}.com'
            )
            vendors.append(vendor)
        self.stdout.write(f"{len(vendors)} vendors created.")

        # --- Create Travel Packages ---
        package_names = ['Parisian Dream', 'Roman Holiday', 'Tokyo Express', 'Jungle Expedition', 'Beach Paradise']
        package_locations = ['Paris', 'Rome', 'Tokyo', 'Amazon Rainforest', 'Maldives'] # New list of locations
        package_travel_types = ['Adventure', 'Relaxation', 'Cultural', 'Exploration', 'Luxury'] # New list of travel types
        packages = []
        
        import requests
        from django.core.files.base import ContentFile

        for i in range(USER_COUNT):
            start_date = date.today() + timedelta(days=random.randint(30, 90))
            
            # Fetch image from Unsplash
            image_url = "https://source.unsplash.com/random/800x600?query=travel"
            response = requests.get(image_url)
            image_name = f"travel_package_{i+1}.jpg"
            
            package = TravelPackage.objects.create(
                vendor=random.choice(vendors),
                name=package_names[i],
                description=f'An unforgettable journey: {package_names[i]}.',
                location=random.choice(package_locations), # Assign a dummy location here
                travel_type=random.choice(package_travel_types), # Assign a dummy travel type here
                itinerary=[
                        {"day": 1, "title": "Arrival and Welcome", "description": "Arrive at your destination, check into your hotel, and enjoy a welcome dinner."},
                        {"day": 2, "title": "City Exploration", "description": "A guided tour of the city's main attractions and landmarks."},
                        {"day": 3, "title": "Cultural Experience", "description": "Visit local markets and museums, and experience the local culture."},
                        {"day": 4, "title": "Free Day", "description": "Enjoy a free day to explore on your own or relax."},
                        {"day": 5, "title": "Departure", "description": "Enjoy a final breakfast before heading to the airport for your departure."}
                    ],
                    price=random.uniform(999.99, 4999.99),
                    start_date=start_date,
                    end_date=start_date + timedelta(days=random.randint(5, 14))
                )
                
            # Save the downloaded image to the package
            if response.status_code == 200:
                package.image.save(image_name, ContentFile(response.content), save=True)
            
            packages.append(package)
        self.stdout.write(f"{len(packages)} travel packages created.")

        # --- Create Bookings ---
        bookings = []
        for i in range(USER_COUNT):
            package = random.choice(packages)
            travelers_count = random.randint(1, 4)
            booking = Booking.objects.create(
                user=random.choice(travelers),
                package=package,
                status=random.choice(['pending', 'confirmed', 'cancelled']),
                number_of_travelers=travelers_count,
                total_price=package.price * travelers_count
            )
            bookings.append(booking)
        self.stdout.write(f"{len(bookings)} bookings created.")

        # --- Create Reviews ---
        reviews = []
        review_comments = [
            "An amazing experience, would definitely recommend!",
            "It was good, but could have been better organized.",
            "Absolutely fantastic from start to finish.",
            "A bit overpriced for what was offered.",
            "The best trip of my life! Unforgettable."
        ]
        for i in range(USER_COUNT):
            # Ensure user has a confirmed booking for the package they are reviewing
            confirmed_bookings = Booking.objects.filter(status='confirmed')
            if confirmed_bookings.exists():
                random_booking = random.choice(list(confirmed_bookings))
                review = Review.objects.create(
                    user=random_booking.user,
                    package=random_booking.package,
                    rating=random.randint(3, 5),
                    comment=random.choice(review_comments),
                    is_verified=True 
                )
                reviews.append(review)
        self.stdout.write(f"{len(reviews)} reviews created.")
        self.stdout.write(self.style.SUCCESS('Successfully seeded the database.'))
