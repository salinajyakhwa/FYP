from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from main.models import Vendor, TravelPackage, UserProfile
from decimal import Decimal
import datetime

class Command(BaseCommand):
    help = 'Seeds the database with 2 vendors, each with 3 detailed Nepal-based packages.'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding detailed Nepal data...')

        # Clear existing data for a clean slate
        #TravelPackage.objects.all().delete()
        #vendor.objects.all().delete()
        #User.objects.filter(is_superuser=False).delete()

        vendors_data = [
            {
                'username': 'himalayan_adventures',
                'name': 'Himalayan Adventures Inc.',
                'desc': 'Your expert guide to the high Himalayas. We specialize in trekking and peak climbing.',
                'packages': [
                    {
                        'name': 'Annapurna Circuit Trek',
                        'location': 'Annapurna Region, Nepal',
                        'travel_type': 'Trekking',
                        'price': Decimal('2100.00'),
                        'start_date': datetime.date(2024, 11, 10),
                        'end_date': datetime.date(2024, 11, 22),
                        'itinerary': [
                            {'day': 1, 'title': 'Arrival in Kathmandu & Welcome Dinner', 'description': 'Arrive at Tribhuvan International Airport. Transfer to your hotel and enjoy a traditional Nepali welcome dinner.'},
                            {'day': 2, 'title': 'Drive to Besisahar, Trek to Bhulbhule', 'description': 'A scenic 6-hour drive to Besisahar, followed by a short trek to Bhulbhule along the Marsyangdi River.'},
                            {'day': 3, 'title': 'Trek to Chame', 'description': 'The trail offers stunning views of Manaslu and Peak 29. We pass through several traditional Gurung villages.'},
                            {'day': 4, 'title': 'Trek to Pisang', 'description': 'Hike through dense forests and witness the dramatic change in landscape as we enter the upper Manang district.'},
                            {'day': 5, 'title': 'Trek to Manang', 'description': 'A relatively easy day to acclimatize. Explore the village of Manang and its ancient monasteries.'},
                            {'day': 6, 'title': 'Acclimatization Day in Manang', 'description': 'Hike to Gangapurna Lake or the Ice Lake for acclimatization and spectacular views.'},
                            {'day': 7, 'title': 'Trek to Yak Kharka', 'description': 'Ascend towards the Thorong La Pass, stopping at the high-altitude settlement of Yak Kharka.'},
                            {'day': 8, 'title': 'Trek to Thorong Phedi', 'description': 'A short but steep climb to the base of the pass. Rest and prepare for the big day tomorrow.'},
                            {'day': 9, 'title': 'Cross Thorong La Pass (5,416m), Trek to Muktinath', 'description': 'The highlight of the trek! An early start to cross the challenging Thorong La Pass, followed by a descent to the sacred pilgrimage site of Muktinath.'},
                            {'day': 10, 'title': 'Drive to Jomsom, Fly to Pokhara', 'description': 'A scenic drive through the Kali Gandaki gorge to Jomsom, followed by a short flight to the beautiful city of Pokhara.'},
                            {'day': 11, 'title': 'Relaxation Day in Pokhara', 'description': 'Enjoy a well-deserved rest day in Pokhara. Boating on Phewa Lake, exploring Lakeside, or simply relaxing.'},
                            {'day': 12, 'title': 'Drive back to Kathmandu', 'description': 'A 6-7 hour scenic drive back to the capital city.'},
                            {'day': 13, 'title': 'Departure', 'description': 'Transfer to the airport for your final departure.'},
                        ]
                    },
                    {
                        'name': 'Langtang Valley Trek',
                        'location': 'Langtang Region, Nepal',
                        'travel_type': 'Trekking',
                        'price': Decimal('950.00'),
                        'start_date': datetime.date(2024, 10, 5),
                        'end_date': datetime.date(2024, 10, 12),
                        'itinerary': [
                            {'day': 1, 'title': 'Drive to Syabrubesi', 'description': 'A 7-8 hour drive from Kathmandu to the starting point of our trek, Syabrubesi.'},
                            {'day': 2, 'title': 'Trek to Lama Hotel', 'description': 'Follow the Langtang Khola river, trekking through dense rhododendron and oak forests.'},
                            {'day': 3, 'title': 'Trek to Langtang Village', 'description': 'The valley opens up, offering views of Langtang Lirung. We pass through the rebuilt Langtang Village.'},
                            {'day': 4, 'title': 'Trek to Kyanjin Gompa', 'description': 'A short trek to the stunning Kyanjin Gompa, an ancient monastery with panoramic mountain views.'},
                            {'day': 5, 'title': 'Explore Tserko Ri', 'description': 'An optional day hike to Tserko Ri (5,000m) for breathtaking 360-degree views of the Langtang range.'},
                            {'day': 6, 'title': 'Trek back to Lama Hotel', 'description': 'Retrace our steps back down the valley.'},
                            {'day': 7, 'title': 'Trek to Syabrubesi', 'description': 'Our final day of trekking.'},
                            {'day': 8, 'title': 'Drive back to Kathmandu', 'description': 'Return to Kathmandu and enjoy a farewell dinner.'},
                        ]
                    },
                    {
                        'name': 'Gokyo Lakes Trek',
                        'location': 'Gokyo Valley, Nepal',
                        'travel_type': 'Trekking',
                        'price': Decimal('1600.00'),
                        'start_date': datetime.date(2025, 3, 15),
                        'end_date': datetime.date(2025, 3, 28),
                        'itinerary': [
                            {'day': 1, 'title': 'Fly to Lukla, Trek to Phakding', 'description': 'An exhilarating flight to Lukla, followed by a short trek to Phakding.'},
                            {'day': 2, 'title': 'Trek to Namche Bazaar', 'description': 'Enter Sagarmatha National Park and make the steep ascent to the Sherpa capital, Namche Bazaar.'},
                            {'day': 3, 'title': 'Acclimatization in Namche', 'description': 'Hike to the Everest View Hotel for stunning panoramas of Everest, Lhotse, and Ama Dablam.'},
                            {'day': 4, 'title': 'Trek to Dole', 'description': 'The trail climbs high above the Dudh Koshi river, offering spectacular views.'},
                            {'day': 5, 'title': 'Trek to Machhermo', 'description': 'Continue ascending through the valley, with views of Cho Oyu becoming prominent.'},
                            {'day': 6, 'title': 'Trek to Gokyo', 'description': 'Reach the stunning turquoise waters of the Gokyo Lakes. Explore the first and second lakes.'},
                            {'day': 7, 'title': 'Explore Gokyo Ri', 'description': 'A pre-dawn hike to the summit of Gokyo Ri (5,357m) for one of the best panoramic views in the Himalayas, including Everest, Lhotse, Makalu, and Cho Oyu.'},
                            {'day': 8, 'title': 'Trek back to Dole', 'description': 'Begin our descent back down the valley.'},
                            {'day': 9, 'title': 'Trek back to Namche Bazaar', 'description': 'Enjoy the familiar trail and the comforts of Namche.'},
                            {'day': 10, 'title': 'Trek to Lukla', 'description': 'The final day of trekking, a long but rewarding descent to Lukla.'},
                            {'day': 11, 'title': 'Fly back to Kathmandu', 'description': 'An early morning flight back to the capital.'},
                            {'day': 12, 'title': 'Contingency Day', 'description': 'A buffer day in case of flight delays from Lukla.'},
                            {'day': 13, 'title': 'Departure', 'description': 'Transfer to the airport for your final departure.'},
                        ]
                    }
                ]
            },
            {
                'username': 'terai_escapes',
                'name': 'Terai Escapes & Safaris',
                'desc': "Discover the lush jungles and rich culture of Nepal's southern plains.",
                'packages': [
                    {
                        'name': 'Bardiya National Park Safari',
                        'location': 'Bardiya, Nepal',
                        'travel_type': 'Wildlife',
                        'price': Decimal('850.00'),
                        'start_date': datetime.date(2024, 12, 1),
                        'end_date': datetime.date(2024, 12, 5),
                        'itinerary': [
                            {'day': 1, 'title': 'Fly to Nepalgunj, Drive to Bardiya', 'description': 'A short flight to Nepalgunj, followed by a drive to our jungle lodge on the edge of Bardiya National Park.'},
                            {'day': 2, 'title': 'Full Day Jeep Safari', 'description': 'Explore the vast grasslands and riverine forests of Bardiya in search of the Royal Bengal Tiger, one-horned rhinos, and wild elephants.'},
                            {'day': 3, 'title': 'Jungle Walk and Tharu Village Tour', 'description': 'An experienced guide will lead you on a jungle walk to track wildlife. In the evening, visit a local Tharu village to experience their unique culture.'},
                            {'day': 4, 'title': 'Canoe Trip and Bird Watching', 'description': 'A serene canoe trip on the Karnali River, home to the gharial and marsh mugger crocodiles, as well as a vast array of birdlife.'},
                            {'day': 5, 'title': 'Drive to Nepalgunj, Fly to Kathmandu', 'description': 'Return to Kathmandu with unforgettable memories of the jungle.'},
                        ]
                    },
                    {
                        'name': 'Lumbini Spiritual Journey',
                        'location': 'Lumbini, Nepal',
                        'travel_type': 'Cultural',
                        'price': Decimal('500.00'),
                        'start_date': datetime.date(2025, 2, 20),
                        'end_date': datetime.date(2025, 2, 22),
                        'itinerary': [
                            {'day': 1, 'title': 'Fly to Bhairahawa, Drive to Lumbini', 'description': 'Fly to Bhairahawa and drive to Lumbini, the sacred birthplace of Lord Buddha.'},
                            {'day': 2, 'title': 'Explore the Sacred Garden', 'description': 'A full day exploring the UNESCO World Heritage site, including the Ashokan Pillar, the Maya Devi Temple, and the various international monastic zones.'},
                            {'day': 3, 'title': 'Tilaurakot & Departure', 'description': 'Visit the ancient ruins of Tilaurakot, the capital of the Shakya kingdom, before driving back to Bhairahawa for your flight to Kathmandu.'},
                        ]
                    },
                    {
                        'name': 'Ilam Tea Garden Retreat',
                        'location': 'Ilam, Nepal',
                        'travel_type': 'Relaxation',
                        'price': Decimal('700.00'),
                        'start_date': datetime.date(2025, 4, 10),
                        'end_date': datetime.date(2025, 4, 14),
                        'itinerary': [
                            {'day': 1, 'title': 'Fly to Bhadrapur, Drive to Ilam', 'description': 'A scenic flight to Bhadrapur in Eastern Nepal, followed by a beautiful drive up to the rolling tea hills of Ilam.'},
                            {'day': 2, 'title': 'Tea Garden Tour & Tasting', 'description': 'Visit a local tea estate to learn about the process of tea making, from plucking the leaves to the final product. Enjoy a professional tea tasting session.'},
                            {'day': 3, 'title': 'Hike to Sandakpur Viewpoint', 'description': 'An early morning hike or drive to Sandakpur for a chance to see a panoramic sunrise over Kanchenjunga, Makalu, and Everest.'},
                            {'day': 4, 'title': 'Explore Fikkal Bazaar and Local Culture', 'description': 'Visit the bustling local market of Fikkal and interact with the local communities.'},
                            {'day': 5, 'title': 'Drive to Bhadrapur, Fly to Kathmandu', 'description': 'Depart from the serene hills of Ilam and fly back to Kathmandu.'},
                        ]
                    }
                ]
            }
        ]

        for vendor_data in vendors_data:
            # Create Vendor User
            user, created = User.objects.get_or_create(
                username=vendor_data['username'],
                defaults={'first_name': vendor_data['name'].split(' ')[0], 'email': f"{vendor_data['username']}@example.com", 'is_staff': True}
            )
            if created:
                user.set_password('password123')
                user.save()

            # Create UserProfile
            profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': 'vendor', 'is_verified': True})

            # Create Vendor
            vendor, _ = Vendor.objects.get_or_create(
                user_profile=profile,
                defaults={'name': vendor_data['name'], 'description': vendor_data['desc'], 'status': 'approved'}
            )
            self.stdout.write(self.style.SUCCESS(f"Seeded Vendor: {vendor.name}"))

            # Create Packages for the Vendor
            for package_data in vendor_data['packages']:
                package_defaults = package_data.copy()
                package, created = TravelPackage.objects.get_or_create(
                    name=package_data['name'],
                    vendor=vendor,
                    defaults=package_defaults
                )
                if created:
                    self.stdout.write(f"  -> Seeded Package: {package.name}")
