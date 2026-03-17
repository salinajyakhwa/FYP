from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from main.models import Vendor, TravelPackage, UserProfile
from decimal import Decimal
import datetime

class Command(BaseCommand):
    help = 'Seeds the database with 3 vendors, 1 traveler, and 3 detailed Nepal-based travel packages.'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding database with detailed Nepal data...')

        # Clean up old data to ensure a fresh start
        User.objects.filter(username__in=['himalayan_peaks', 'annapurna_adventures', 'jungle_explorers', 'traveler_user']).delete()

        # --- Create Traveler User ---
        traveler_user, created = User.objects.get_or_create(
            username='traveler_user',
            defaults={'first_name': 'Sam', 'last_name': 'Traveler', 'email': 'traveler@example.com'}
        )
        if created:
            traveler_user.set_password('password123')
            traveler_user.save()
        UserProfile.objects.get_or_create(user=traveler_user, defaults={'role': 'traveler', 'is_verified': True})
        self.stdout.write(self.style.SUCCESS('Successfully created traveler user: traveler_user'))

        # --- Define Vendor and Package Data ---
        nepal_data = [
            {
                'vendor_username': 'himalayan_peaks',
                'vendor_name': 'Himalayan Peaks Expeditions',
                'vendor_desc': 'Your expert guide to the roof of the world. We specialize in safe, memorable, and breathtaking treks in the Everest region.',
                'package': {
                    'name': 'Everest Base Camp Sanctuary Trek',
                    'description': 'Embark on a 14-day journey to the foot of Mount Everest. This trek takes you through the heart of the Khumbu region, offering stunning panoramic views of Everest, Lhotse, Nuptse, and Ama Dablam. Experience the unique culture of the Sherpa people in vibrant villages like Namche Bazaar.',
                    'location': 'Everest Region, Nepal',
                    'travel_type': 'Adventure',
                    'price': Decimal('1950.00'),
                    'start_date': datetime.date(2024, 10, 1),
                    'end_date': datetime.date(2024, 10, 14),
                    'itinerary': [
                        {'day': 1, 'title': 'Arrival in Kathmandu & Trip Preparation', 'description': 'Arrive at Tribhuvan International Airport, transfer to your hotel. In the evening, meet your guide for a trip briefing and gear check.'},
                        {'day': 2, 'title': 'Fly to Lukla, Trek to Phakding', 'description': 'An early morning scenic flight to Lukla (2,860m), the gateway to the Everest region. Begin your trek downhill to the village of Phakding.'},
                        {'day': 3, 'title': 'Trek to Namche Bazaar', 'description': 'Follow the Dudh Koshi river, crossing several suspension bridges, including the famous Hillary Bridge. A steep ascent brings you to Namche Bazaar (3,440m), the main trading hub of the Khumbu.'},
                        {'day': 4, 'title': 'Acclimatization Day in Namche', 'description': 'Hike to the Everest View Hotel for your first glimpse of Mount Everest. Explore the Sherpa museum and the vibrant market of Namche.'},
                        {'day': 5, 'title': 'Trek to Tengboche', 'description': 'A beautiful trail with stunning views of Ama Dablam. Descend to the river and then climb to Tengboche (3,860m), home to the largest monastery in the region.'},
                    ]
                }
            },
            {
                'vendor_username': 'annapurna_adventures',
                'vendor_name': 'Annapurna Alpine Adventures',
                'vendor_desc': 'Discover the diverse beauty of the Annapurna massif, from lush forests to arid high-altitude landscapes.',
                'package': {
                    'name': 'Annapurna Circuit Discovery',
                    'description': 'A classic 12-day trek that circles the Annapurna massif. This route offers unparalleled scenic and cultural diversity, passing through rhododendron forests, subtropical valleys, and the arid, windswept landscapes of the Tibetan plateau.',
                    'location': 'Annapurna Region, Nepal',
                    'travel_type': 'Trekking',
                    'price': Decimal('1600.00'),
                    'start_date': datetime.date(2024, 11, 5),
                    'end_date': datetime.date(2024, 11, 16),
                    'itinerary': [
                        {'day': 1, 'title': 'Drive to Besisahar and Trek to Bhulbhule', 'description': 'A scenic drive from Kathmandu to Besisahar. Begin the trek with a short walk to the village of Bhulbhule.'},
                        {'day': 2, 'title': 'Trek to Ghermu', 'description': 'The trail follows the Marsyangdi River, passing through terraced fields and traditional Gurung villages.'},
                        {'day': 3, 'title': 'Trek to Tal', 'description': 'Continue along the river, with the landscape becoming more rugged. Tal is a former lakebed, creating a wide, flat valley.'},
                        {'day': 4, 'title': 'Trek to Chame', 'description': 'Enter the Manang district. The trail offers great views of Annapurna II and Pisang Peak. Chame is the administrative headquarters of the region.'},
                    ]
                }
            },
            {
                'vendor_username': 'jungle_explorers',
                'vendor_name': 'Jungle Explorer Nepal',
                'vendor_desc': 'Experience the wild heart of Nepal in the lush plains of the Terai. We offer ethical and exciting wildlife safaris.',
                'package': {
                    'name': 'Chitwan National Park Wildlife Safari',
                    'description': 'A 4-day immersive safari in the UNESCO World Heritage site of Chitwan National Park. Explore the grasslands and forests to spot the one-horned rhinoceros, elephants, crocodiles, and if you are lucky, the elusive Royal Bengal Tiger.',
                    'location': 'Chitwan, Nepal',
                    'travel_type': 'Wildlife',
                    'price': Decimal('550.00'),
                    'start_date': datetime.date(2024, 9, 20),
                    'end_date': datetime.date(2024, 9, 23),
                    'itinerary': [
                        {'day': 1, 'title': 'Arrival and Tharu Village Tour', 'description': 'Arrive at your jungle lodge in Sauraha. In the evening, take a tour of a nearby Tharu village to learn about their unique culture and lifestyle.'},
                        {'day': 2, 'title': 'Jungle Activities', 'description': 'A full day of activities including a canoe trip on the Rapti River to see crocodiles, a jungle walk with an expert guide, and an afternoon jeep safari deep into the park.'},
                        {'day': 3, 'title': 'Elephant Breeding Center and Cultural Show', 'description': 'Visit the elephant breeding center to see baby elephants. In the evening, enjoy a traditional Tharu cultural dance performance.'},
                    ]
                }
            }
        ]

        # --- Loop and Create Data ---
        for data in nepal_data:
            vendor_user, created = User.objects.get_or_create(
                username=data['vendor_username'],
                defaults={'email': f"{data['vendor_username']}@example.com"}
            )
            if created:
                vendor_user.set_password('password123')
                vendor_user.save()
            
            vendor_profile, _ = UserProfile.objects.get_or_create(user=vendor_user, defaults={'role': 'vendor', 'is_verified': True})
            
            vendor, _ = Vendor.objects.get_or_create(
                user_profile=vendor_profile,
                defaults={'name': data['vendor_name'], 'description': data['vendor_desc'], 'status': 'approved'}
            )
            
            package_defaults = {k: v for k, v in data['package'].items() if k not in ['available_slots']}
            package, created = TravelPackage.objects.get_or_create(
                name=data['package']['name'],
                vendor=vendor,
                defaults=package_defaults
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created package: {package.name}"))

        self.stdout.write(self.style.SUCCESS('Successfully seeded detailed Nepal data.'))
