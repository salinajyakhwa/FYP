from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import BookingTravelerForm
from .models import Booking, BookingCapacityRequest, Review, TravelPackage, UserProfile, Vendor
from .services.capacity import can_proceed_with_capacity
from .services.payments import _calculate_booking_pricing


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


class VendorPackageDeletionTests(TestCase):
    def setUp(self):
        self.vendor_user = User.objects.create_user(username='vendor_delete', password='pass12345')
        self.traveler = User.objects.create_user(username='traveler_delete', password='pass12345')
        self.vendor_profile = UserProfile.objects.create(user=self.vendor_user, role='vendor')
        self.traveler_profile = UserProfile.objects.create(user=self.traveler, role='traveler')
        self.vendor = Vendor.objects.create(
            user_profile=self.vendor_profile,
            name='Delete Test Vendor',
            description='Vendor description',
            status='approved',
        )
        self.package = TravelPackage.objects.create(
            vendor=self.vendor,
            name='Delete Me',
            description='Package description',
            location='Nepal',
            travel_type='Trek',
            price=Decimal('450.00'),
            max_travelers=10,
            start_date=timezone.now().date() + timedelta(days=10),
            end_date=timezone.now().date() + timedelta(days=15),
        )

    def test_vendor_can_delete_unused_package(self):
        self.client.login(username='vendor_delete', password='pass12345')

        response = self.client.post(
            reverse('delete_package', args=[self.package.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(TravelPackage.objects.filter(id=self.package.id).exists())

    def test_vendor_cannot_delete_package_with_booking(self):
        Booking.objects.create(
            user=self.traveler,
            package=self.package,
            total_price=Decimal('450.00'),
            status='confirmed',
        )
        self.client.login(username='vendor_delete', password='pass12345')

        response = self.client.post(
            reverse('delete_package', args=[self.package.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(TravelPackage.objects.filter(id=self.package.id).exists())
        self.assertContains(response, 'This package cannot be deleted')


class TravelerPricingRulesTests(TestCase):
    def setUp(self):
        self.vendor_user = User.objects.create_user(username='vendor_pricing', password='pass12345')
        self.traveler = User.objects.create_user(username='traveler_pricing', password='pass12345')
        self.vendor_profile = UserProfile.objects.create(user=self.vendor_user, role='vendor')
        self.traveler_profile = UserProfile.objects.create(user=self.traveler, role='traveler')
        self.vendor = Vendor.objects.create(
            user_profile=self.vendor_profile,
            name='Pricing Vendor',
            description='Vendor description',
            status='approved',
        )
        self.package = TravelPackage.objects.create(
            vendor=self.vendor,
            name='Family Package',
            description='Package description',
            location='Nepal',
            travel_type='Tour',
            price=Decimal('500.00'),
            max_travelers=10,
            start_date=timezone.now().date() + timedelta(days=10),
            end_date=timezone.now().date() + timedelta(days=15),
        )

    def test_booking_pricing_excludes_children_under_seven_from_total(self):
        pricing = _calculate_booking_pricing(
            self.package,
            adult_count=2,
            child_count=1,
            child_under_seven_count=2,
        )

        self.assertEqual(pricing['total_travelers'], 5)
        self.assertEqual(pricing['total_price'], Decimal('1500.00'))

    def test_traveler_form_counts_children_under_seven_in_total_travelers(self):
        form = BookingTravelerForm(
            data={'adult_count': 2, 'child_count': 1, 'child_under_seven_count': 2}
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.total_travelers(), 5)
        self.assertEqual(form.calculate_total(Decimal('500.00'), Decimal('500.00')), Decimal('1500.00'))

    def test_capacity_check_counts_children_under_seven(self):
        Booking.objects.create(
            user=self.traveler,
            package=self.package,
            total_price=Decimal('1000.00'),
            status='confirmed',
            adult_count=2,
            child_count=0,
            child_under_seven_count=0,
            number_of_travelers=2,
        )
        self.package.max_travelers = 4
        self.package.save(update_fields=['max_travelers'])

        allowed, approved_request, summary = can_proceed_with_capacity(
            traveler=self.traveler,
            package=self.package,
            adult_count=1,
            child_count=0,
            child_under_seven_count=2,
        )

        self.assertFalse(allowed)
        self.assertIsNone(approved_request)
        self.assertEqual(summary['remaining_capacity'], 2)


class VendorCapacityRequestReviewTests(TestCase):
    def setUp(self):
        self.vendor_user = User.objects.create_user(username='vendor_capacity', password='pass12345')
        self.traveler = User.objects.create_user(username='traveler_capacity', password='pass12345')
        self.vendor_profile = UserProfile.objects.create(user=self.vendor_user, role='vendor')
        self.traveler_profile = UserProfile.objects.create(user=self.traveler, role='traveler')
        self.vendor = Vendor.objects.create(
            user_profile=self.vendor_profile,
            name='Capacity Vendor',
            description='Vendor description',
            status='approved',
        )
        self.package = TravelPackage.objects.create(
            vendor=self.vendor,
            name='Capacity Package',
            description='Package description',
            location='Nepal',
            travel_type='Tour',
            price=Decimal('800.00'),
            max_travelers=2,
            start_date=timezone.now().date() + timedelta(days=10),
            end_date=timezone.now().date() + timedelta(days=15),
        )
        self.capacity_request = BookingCapacityRequest.objects.create(
            package=self.package,
            traveler=self.traveler,
            adult_count=2,
            child_count=1,
            child_under_seven_count=0,
            number_of_travelers=3,
        )

    def test_vendor_can_approve_own_capacity_request(self):
        self.client.login(username='vendor_capacity', password='pass12345')

        response = self.client.post(
            reverse('review_capacity_request', args=[self.capacity_request.id, 'approve']),
            {'vendor_notes': 'Approved'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.capacity_request.refresh_from_db()
        self.assertEqual(self.capacity_request.status, 'approved')
        notification = self.traveler.notifications.get(dedupe_key=f'capacity-approved:{self.capacity_request.id}')
        self.assertIn(reverse('choose_payment', args=[self.package.id]), notification.target_url)
        self.assertIn('adult_count=2', notification.target_url)
        self.assertIn('child_count=1', notification.target_url)
        self.assertIn(f'capacity_request_id={self.capacity_request.id}', notification.target_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.traveler.email])
        self.assertIn('approved', mail.outbox[0].subject.lower())
        self.assertIn(reverse('choose_payment', args=[self.package.id]), mail.outbox[0].body)


class CustomItineraryConfirmationTests(TestCase):
    def setUp(self):
        self.traveler = User.objects.create_user(username='traveler_custom', password='pass12345')
        self.vendor_user = User.objects.create_user(username='vendor_custom', password='pass12345')
        self.traveler_profile = UserProfile.objects.create(user=self.traveler, role='traveler')
        self.vendor_profile = UserProfile.objects.create(user=self.vendor_user, role='vendor')
        self.vendor = Vendor.objects.create(
            user_profile=self.vendor_profile,
            name='Custom Vendor',
            description='Vendor description',
            status='approved',
        )
        self.package = TravelPackage.objects.create(
            vendor=self.vendor,
            name='Custom Package',
            description='Package description',
            location='Nepal',
            travel_type='Tour',
            price=Decimal('1000.00'),
            max_travelers=10,
            start_date=timezone.now().date() + timedelta(days=10),
            end_date=timezone.now().date() + timedelta(days=15),
        )
        self.day_one = self.package.package_days.create(day_number=1, title='Arrival', description='Day one')
        self.option_one = self.day_one.options.create(
            option_type='flight',
            title='Morning Flight',
            description='Flight option',
            additional_cost=Decimal('150.00'),
        )

    def test_custom_booking_confirmation_creates_custom_itinerary(self):
        self.client.login(username='traveler_custom', password='pass12345')

        response = self.client.post(
            reverse('custom_booking_confirmation', args=[self.package.id]),
            {f'day_{self.day_one.id}': str(self.option_one.id)},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        custom_itinerary = self.traveler.custom_itineraries.get(package=self.package)
        self.assertEqual(custom_itinerary.final_price, Decimal('1150.00'))
        self.assertEqual(custom_itinerary.selections.count(), 1)
        self.assertContains(response, 'Customization Confirmation')
