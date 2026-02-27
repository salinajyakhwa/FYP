import random
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from main.models import Vendor, TravelPackage, UserProfile
from decimal import Decimal
import datetime

class Command(BaseCommand):
    help = 'Seeds the database with 3 vendors and 3 Nepal-based travel packages.'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding Nepal data...')

        # 1. Define Vendor and Package Data
        nepal_data = [
            {
                'vendor_username': 'everest_treks',
                'vendor_name': 'Everest View Treks',
                'vendor_desc': 'Leading treks to the heart of the Himalayas.',
                'package': {
                    'name': 'Everest Base Camp Trek',
                    'description': 'A 14-day trek to the base of the world\'s highest peak, offering breathtaking views of Everest, Lhotse, and Ama Dablam.',
                    'location': 'Khumbu Region, Nepal',
                    'travel_type': 'Adventure',
                    'price': Decimal('1800.00'),
                    'start_date': datetime.date(2024, 10, 1),
                    'end_date': datetime.date(2024, 10, 14),
                }
            },
            {
                'vendor_username': 'pokhara_paragliding',
                'vendor_name': 'Pokhara Sky Adventures',
                'vendor_desc': 'Experience the thrill of paragliding over the beautiful Phewa Lake.',
                'package': {
                    'name': 'Paragliding Over Pokhara',
                    'description': 'A 3-day adventure package in Pokhara, including a tandem paragliding flight with stunning views of the Annapurna range.',
                    'location': 'Pokhara, Nepal',
                    'travel_type': 'Adventure',
                    'price': Decimal('450.00'),
                    'start_date': datetime.date(2024, 11, 5),
                    'end_date': datetime.date(2024, 11, 7),
                }
            },
            {
                'vendor_username': 'chitwan_safari',
                'vendor_name': 'Chitwan Jungle Safaris',
                'vendor_desc': 'Explore the diverse wildlife of Chitwan National Park.',
                'package': {
                    'name': 'Chitwan Wildlife Safari',
                    'description': 'A 4-day safari adventure in Chitwan National Park, featuring jeep tours, canoe trips, and the chance to see rhinos, elephants, and tigers.',
                    'location': 'Chitwan National Park, Nepal',
                    'travel_type': 'Wildlife',
                    'price': Decimal('600.00'),
                    'start_date': datetime.date(2024, 9, 15),
                    'end_date': datetime.date(2024, 9, 18),
                }
            }
        ]

        # 2. Loop through data and create objects
        for data in nepal_data:
            # Create Vendor User
            vendor_user, created = User.objects.get_or_create(
                username=data['vendor_username'],
                defaults={'email': f"{data['vendor_username']}@example.com"}
            )
            if created:
                vendor_user.set_password('password123')
                vendor_user.save()
                self.stdout.write(f"Created user: {data['vendor_username']}")

            # Create UserProfile
            vendor_profile, _ = UserProfile.objects.get_or_create(
                user=vendor_user,
                defaults={'role': 'vendor', 'is_verified': True}
            )

            # Create Vendor
            vendor, _ = Vendor.objects.get_or_create(
                user_profile=vendor_profile,
                defaults={
                    'name': data['vendor_name'],
                    'description': data['vendor_desc'],
                    'status': 'approved'
                }
            )
            self.stdout.write(f"Created vendor: {vendor.name}")

            # Create Package
            package_data = data['package']
            package, created = TravelPackage.objects.get_or_create(
                name=package_data['name'],
                vendor=vendor,
                defaults=package_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"  -> Created package: {package.name}"))
            else:
                self.stdout.write(self.style.WARNING(f"  -> Package '{package.name}' already exists. Skipping."))

        self.stdout.write(self.style.SUCCESS('Successfully seeded Nepal data.'))
