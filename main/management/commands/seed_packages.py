from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from main.models import Vendor, TravelPackage, UserProfile
from decimal import Decimal
import datetime

class Command(BaseCommand):
    help = 'Seeds the database with 5 sample travel packages.'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')

        # 1. Find or create a vendor user
        vendor_user, created = User.objects.get_or_create(
            username='wonderlust_adventures', 
            defaults={
                'first_name': 'Alex',
                'last_name': 'Wander',
                'email': 'vendor@example.com',
            }
        )
        if created:
            vendor_user.set_password('vendorpass123')
            vendor_user.save()
            self.stdout.write(self.style.SUCCESS(f'Created vendor user: {vendor_user.username}'))

        # 2. Find or create a user profile for the vendor
        vendor_profile, created = UserProfile.objects.get_or_create(
            user=vendor_user,
            defaults={'role': 'vendor', 'is_verified': True}
        )

        # 3. Find or create the Vendor object
        main_vendor, created = Vendor.objects.get_or_create(
            user_profile=vendor_profile,
            defaults={
                'name': 'Wonderlust Adventures',
                'description': 'Curators of unforgettable journeys and experiences.',
                'status': 'approved'
            }
        )
        self.stdout.write(self.style.SUCCESS(f'Using vendor: {main_vendor.name}'))

        # 4. Define 5 sample packages
        packages_data = [
            {
                'name': 'Mystical Bali Getaway',
                'description': 'Explore the spiritual heart of Bali, from lush rice paddies to ancient temples. A journey of culture and relaxation.',
                'location': 'Bali, Indonesia',
                'travel_type': 'Cultural',
                'price': Decimal('1250.00'),
                'start_date': datetime.date(2024, 7, 10),
                'end_date': datetime.date(2024, 7, 17),
            },
            {
                'name': 'Parisian Romance & Art',
                'description': 'Discover the magic of Paris. Visit the Louvre, stroll along the Seine, and enjoy world-class cuisine.',
                'location': 'Paris, France',
                'travel_type': 'Romantic',
                'price': Decimal('1800.00'),
                'start_date': datetime.date(2024, 8, 5),
                'end_date': datetime.date(2024, 8, 12),
            },
            {
                'name': 'Alaskan Wilderness Expedition',
                'description': 'Witness the raw beauty of Alaska. See glaciers, wildlife, and the stunning northern lights on this adventure of a lifetime.',
                'location': 'Alaska, USA',
                'travel_type': 'Adventure',
                'price': Decimal('2500.00'),
                'start_date': datetime.date(2024, 9, 1),
                'end_date': datetime.date(2024, 9, 10),
            },
            {
                'name': 'Secrets of Ancient Rome',
                'description': 'Walk in the footsteps of emperors and gladiators. Explore the Colosseum, Roman Forum, and Vatican City.',
                'location': 'Rome, Italy',
                'travel_type': 'Historical',
                'price': Decimal('1500.00'),
                'start_date': datetime.date(2024, 10, 15),
                'end_date': datetime.date(2024, 10, 22),
            },
            {
                'name': 'Tokyo: Tradition & Future',
                'description': 'Experience the vibrant contrast of Tokyo, from serene temples and gardens to bustling cityscapes and futuristic technology.',
                'location': 'Tokyo, Japan',
                'travel_type': 'Urban',
                'price': Decimal('2100.00'),
                'start_date': datetime.date(2024, 11, 20),
                'end_date': datetime.date(2024, 11, 27),
            },
        ]

        # 5. Create the TravelPackage objects
        for package_data in packages_data:
            package, created = TravelPackage.objects.get_or_create(
                name=package_data['name'],
                vendor=main_vendor,
                defaults=package_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created package: "{package.name}"'))
            else:
                self.stdout.write(self.style.WARNING(f'Package "{package.name}" already exists. Skipping.'))

        self.stdout.write(self.style.SUCCESS('Data seeding complete.'))
