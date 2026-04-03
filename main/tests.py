from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Booking, Review, TravelPackage, UserProfile, Vendor


class ReviewFlowTests(TestCase):
    def setUp(self):
        self.traveler = User.objects.create_user(username='traveler', password='pass12345')
        self.vendor_user = User.objects.create_user(username='vendor', password='pass12345')

        self.traveler_profile = UserProfile.objects.create(user=self.traveler, role='traveler')
        self.vendor_profile = UserProfile.objects.create(user=self.vendor_user, role='vendor')
        self.vendor = Vendor.objects.create(
            user_profile=self.vendor_profile,
            name='Test Vendor',
            description='Vendor description',
            status='approved',
        )
        self.package = TravelPackage.objects.create(
            vendor=self.vendor,
            name='Everest Base Camp',
            description='Package description',
            location='Nepal',
            travel_type='Trek',
            price=Decimal('999.00'),
            max_travelers=10,
            start_date=timezone.now().date() - timedelta(days=10),
            end_date=timezone.now().date() - timedelta(days=3),
        )

    def test_package_detail_shows_review_form_for_trip_completed_booking(self):
        Booking.objects.create(
            user=self.traveler,
            package=self.package,
            total_price=Decimal('999.00'),
            status='trip_completed',
        )
        self.client.login(username='traveler', password='pass12345')

        response = self.client.get(reverse('package_detail', args=[self.package.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add Review')

    def test_add_review_accepts_trip_completed_booking(self):
        Booking.objects.create(
            user=self.traveler,
            package=self.package,
            total_price=Decimal('999.00'),
            status='trip_completed',
        )
        self.client.login(username='traveler', password='pass12345')

        response = self.client.post(
            reverse('add_review', args=[self.package.id]),
            {'rating': 5, 'comment': 'Excellent trip.'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Review.objects.filter(
                user=self.traveler,
                package=self.package,
                rating=5,
                comment='Excellent trip.',
                is_verified=True,
            ).exists()
        )

    def test_my_bookings_shows_leave_review_button_for_eligible_booking(self):
        booking = Booking.objects.create(
            user=self.traveler,
            package=self.package,
            total_price=Decimal('999.00'),
            status='trip_completed',
        )
        self.client.login(username='traveler', password='pass12345')

        response = self.client.get(reverse('my_bookings'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('package_detail', args=[booking.package.id]) + '#reviews',
        )
        self.assertContains(response, 'Leave Review')

    def test_my_bookings_hides_leave_review_button_after_review_submitted(self):
        booking = Booking.objects.create(
            user=self.traveler,
            package=self.package,
            total_price=Decimal('999.00'),
            status='trip_completed',
        )
        Review.objects.create(
            user=self.traveler,
            package=self.package,
            rating=5,
            comment='Already reviewed.',
            is_verified=True,
        )
        self.client.login(username='traveler', password='pass12345')

        response = self.client.get(reverse('my_bookings'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse('package_detail', args=[booking.package.id]) + '#reviews',
        )
        self.assertContains(response, 'You already reviewed this trip.')
