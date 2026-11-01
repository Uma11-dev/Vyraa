
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from chatbot.models import Booking, Client, HandoffRequest, Notification
from chatbot.services.handoff_service import HandoffService
from chatbot.services.notification_service import NotificationService

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
class ReminderCommandTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(
            client_id="reminder-client",
            full_name="Reminder Client",
            email="reminder@example.com",
            whatsapp="8888888888",
        )

        # Freeze the clock used by the management command.
        self.now = timezone.now()

    def create_booking(self, hours):
        return Booking.objects.create(
            client=self.client_obj,
            service="future_fragments",
            scheduled_at=self.now + timedelta(hours=hours, minutes=5),
            status="confirmed",
        )

    def run_command_at_fixed_time(self):
        with patch(
            "chatbot.management.commands.process_vyra_notifications.timezone.now",
            return_value=self.now,
        ):
            call_command("process_vyra_notifications")

    def test_command_queues_24_hour_reminder(self):
        booking = self.create_booking(24)

        self.run_command_at_fixed_time()

        self.assertTrue(
            Notification.objects.filter(
                booking=booking,
                notification_type="reminder_24h",
            ).exists()
        )

    def test_command_queues_3_hour_reminder(self):
        booking = self.create_booking(3)

        self.run_command_at_fixed_time()

        self.assertTrue(
            Notification.objects.filter(
                booking=booking,
                notification_type="reminder_3h",
            ).exists()
        )

    def test_command_does_not_duplicate_reminders(self):
        booking = self.create_booking(24)

        self.run_command_at_fixed_time()
        self.run_command_at_fixed_time()

        self.assertEqual(
            Notification.objects.filter(
                booking=booking,
                notification_type="reminder_24h",
            ).count(),
            1,
        )
