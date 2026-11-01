from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from chatbot.models import Booking, Client
from chatbot.services.booking.availability_service import AvailabilityService
from chatbot.services.booking.booking_service import BookingService
from chatbot.services.client.client_service import ClientService


@override_settings(TIME_ZONE="Asia/Kolkata", USE_TZ=True)
class BookingServiceTests(TestCase):
    """Regression tests for Luna's Sanctum booking rules."""

    def setUp(self):
        self.client_profile, _ = ClientService.get_or_create_client(
            client_id="booking-test-client"
        )
        ClientService.update_client(
            self.client_profile,
            full_name="Test Client",
            email="test@example.com",
            whatsapp="+919999999999",
            date_of_birth=date(1995, 5, 17),
            birth_time=time(10, 30),
            birth_place="Delhi, India",
        )
        self.client_profile.refresh_from_db()

    def next_working_date(self, days_ahead=4):
        target = timezone.localdate() + timedelta(days=days_ahead)
        while not AvailabilityService.is_working_day(target):
            target += timedelta(days=1)
        return target

    def make_slot(self, days_ahead=4, at=time(11, 0)):
        target_date = self.next_working_date(days_ahead)
        return timezone.make_aware(
            datetime.combine(target_date, at),
            timezone=timezone.get_default_timezone(),
        )

    def test_service_durations_are_correct(self):
        self.assertEqual(BookingService.get_service_duration("future_fragments"), 60)
        self.assertEqual(BookingService.get_service_duration("unseen_alignment"), 75)
        self.assertEqual(BookingService.get_service_duration("karmic_pattern_mapping"), 90)

    def test_invalid_service_is_rejected(self):
        with self.assertRaises(ValueError):
            BookingService.normalize_service("Not a real service")

    def test_minimum_notice_rejects_booking_too_soon(self):
        too_soon = timezone.now() + timedelta(days=2)
        with self.assertRaisesMessage(ValueError, "at least 3 days notice"):
            BookingService.validate_booking_time(too_soon)

    def test_working_days_are_monday_through_saturday(self):
        self.assertTrue(AvailabilityService.is_working_day(date(2026, 10, 12)))
        self.assertFalse(AvailabilityService.is_working_day(date(2026, 10, 11)))

    def test_working_window_uses_configured_local_timezone(self):
        target_date = self.next_working_date()
        start, end = AvailabilityService.get_working_window(target_date)
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertEqual(timezone.localtime(start).time(), time(10, 0))
        self.assertEqual(timezone.localtime(end).time(), time(20, 0))

    def test_booking_can_be_created_for_valid_slot(self):
        booking = BookingService.create_booking(
            client=self.client_profile,
            service="future_fragments",
            scheduled_at=self.make_slot(),
            notes="Booking service test",
        )
        self.assertIsInstance(booking, Booking)
        self.assertEqual(booking.status, "pending")
        self.assertEqual(booking.service, "future_fragments")
        self.assertEqual(Booking.objects.count(), 1)

    def test_pending_booking_can_be_confirmed_inside_three_day_window(self):
        slot = self.make_slot(days_ahead=4)
        booking = BookingService.create_booking(
            client=self.client_profile,
            service="future_fragments",
            scheduled_at=slot,
        )

        # Simulate confirmation when the valid booking is only two days away.
        with patch(
            "chatbot.services.booking.booking_service.timezone.now",
            return_value=slot - timedelta(days=2),
        ):
            confirmed = BookingService.confirm_booking(booking)

        self.assertEqual(confirmed.status, "confirmed")

    def test_cancel_pending_booking(self):
        booking = BookingService.create_booking(
            client=self.client_profile,
            service="future_fragments",
            scheduled_at=self.make_slot(),
        )
        cancelled = BookingService.cancel_booking(booking)
        self.assertEqual(cancelled.status, "cancelled")

    def test_confirmed_booking_can_be_completed(self):
        booking = BookingService.create_booking(
            client=self.client_profile,
            service="future_fragments",
            scheduled_at=self.make_slot(),
        )
        confirmed = BookingService.confirm_booking(booking)
        completed = BookingService.complete_booking(confirmed)
        self.assertEqual(completed.status, "completed")

    def test_completed_booking_cannot_be_cancelled(self):
        booking = BookingService.create_booking(
            client=self.client_profile,
            service="future_fragments",
            scheduled_at=self.make_slot(),
        )
        confirmed = BookingService.confirm_booking(booking)
        completed = BookingService.complete_booking(confirmed)
        with self.assertRaisesMessage(ValueError, "cannot be cancelled"):
            BookingService.cancel_booking(completed)

    def test_overlapping_booking_is_rejected(self):
        slot = self.make_slot(at=time(11, 0))
        BookingService.create_booking(
            client=self.client_profile,
            service="unseen_alignment",
            scheduled_at=slot,
        )
        with self.assertRaisesMessage(ValueError, "overlaps"):
            BookingService.create_booking(
                client=self.client_profile,
                service="future_fragments",
                scheduled_at=slot + timedelta(minutes=60),
            )

    def test_incomplete_profile_is_not_booking_ready(self):
        incomplete_client, _ = ClientService.get_or_create_client(
            client_id="incomplete-booking-test-client"
        )
        from chatbot.services.booking.booking_orchestrator import BookingOrchestrator

        readiness = BookingOrchestrator.get_booking_readiness(incomplete_client)
        self.assertFalse(readiness["ready"])
        self.assertIn("full_name", readiness["missing_fields"])


@override_settings(TIME_ZONE="Asia/Kolkata", USE_TZ=True)
class BookingAPITests(TestCase):
    """API-level tests for the registered booking endpoints."""

    def setUp(self):
        self.api = APIClient()
        self.client_profile, _ = ClientService.get_or_create_client(
            client_id="booking-api-test-client"
        )
        ClientService.update_client(
            self.client_profile,
            full_name="API Test Client",
            email="api-test@example.com",
            whatsapp="+919888888888",
            date_of_birth=date(1994, 4, 12),
            birth_time=time(9, 15),
            birth_place="Delhi, India",
        )
        self.client_profile.refresh_from_db()

    def next_valid_slot(self):
        target = timezone.localdate() + timedelta(days=4)
        while not AvailabilityService.is_working_day(target):
            target += timedelta(days=1)
        slot = timezone.make_aware(
            datetime.combine(target, time(11, 0)),
            timezone=timezone.get_default_timezone(),
        )
        # If a test runs near the current time, ensure the slot satisfies
        # the exact three-day minimum notice as well.
        while slot < timezone.now() + timedelta(days=3):
            target += timedelta(days=1)
            while not AvailabilityService.is_working_day(target):
                target += timedelta(days=1)
            slot = timezone.make_aware(
                datetime.combine(target, time(11, 0)),
                timezone=timezone.get_default_timezone(),
            )
        return slot

    def test_availability_requires_client_id(self):
        response = self.api.post(
            "/api/bookings/availability/",
            {"service": "future_fragments"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_availability_returns_404_for_unknown_client(self):
        response = self.api.post(
            "/api/bookings/availability/",
            {
                "client_id": "does-not-exist",
                "service": "future_fragments",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_availability_reports_incomplete_profile(self):
        incomplete, _ = ClientService.get_or_create_client(
            client_id="incomplete-api-client"
        )
        response = self.api.post(
            "/api/bookings/availability/",
            {
                "client_id": incomplete.client_id,
                "service": "future_fragments",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["reason"], "profile_incomplete")

    def test_create_requires_scheduled_at(self):
        response = self.api.post(
            "/api/bookings/create/",
            {
                "client_id": self.client_profile.client_id,
                "service": "future_fragments",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_invalid_datetime(self):
        response = self.api.post(
            "/api/bookings/create/",
            {
                "client_id": self.client_profile.client_id,
                "service": "future_fragments",
                "scheduled_at": "not-a-date",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_availability_returns_400_for_unknown_service(self):
        response = self.api.post(
            "/api/bookings/availability/",
            {
                "client_id": self.client_profile.client_id,
                "service": "made_up_service",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_endpoint_creates_pending_booking(self):
        response = self.api.post(
            "/api/bookings/create/",
            {
                "client_id": self.client_profile.client_id,
                "service": "future_fragments",
                "scheduled_at": self.next_valid_slot().isoformat(),
                "notes": "API test booking",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["booking"]["status"], "pending")
        self.assertEqual(Booking.objects.filter(client=self.client_profile).count(), 1)
