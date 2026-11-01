
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from chatbot.models import Booking, Notification
from chatbot.services.notification_service import NotificationService

class Command(BaseCommand):
    help = (
        "Queue appointment reminders and deliver due VYRA emails."
    )

    def handle(self, *args, **options):
        now = timezone.now()

        # Queue a reminder once the booking enters each reminder window.
        windows = [
            ("reminder_24h", timedelta(hours=24)),
            ("reminder_3h", timedelta(hours=3)),
        ]

        queued = 0

        for notification_type, lead_time in windows:
            start = now + lead_time
            end = start + timedelta(minutes=15)

            bookings = Booking.objects.filter(
                status="confirmed",
                scheduled_at__gt=start,
                scheduled_at__lte=end,
            ).select_related("client")

            for booking in bookings:
                label = booking.get_service_display()
                appointment_time = timezone.localtime(
                    booking.scheduled_at
                ).strftime("%A, %d %B %Y at %I:%M %p IST")

                if notification_type == "reminder_24h":
                    reminder_text = "Your appointment is tomorrow."
                else:
                    reminder_text = (
                        "Your appointment is coming up in about three hours."
                    )

                result = NotificationService.queue_email(
                    client=booking.client,
                    booking=booking,
                    notification_type=notification_type,
                    subject=f"Reminder: {label} | Luna's Sanctum",
                    message=(
                        f"Hello {booking.client.full_name or 'there'},\n\n"
                        f"{reminder_text}\n\n"
                        f"Service: {label}\n"
                        f"Time: {appointment_time}\n\n"
                        "If you need help with your appointment, "
                        "please contact Luna's Sanctum.\n\n"
                        "With care,\nLuna's Sanctum"
                    ),
                    idempotency_key=(
                        f"booking:{booking.pk}:{notification_type}"
                    ),
                    scheduled_for=now,
                )

                if result.get("created"):
                    queued += 1

        results = NotificationService.process_due()

        self.stdout.write(
            self.style.SUCCESS(
                f"Queued {queued} reminder(s); "
                f"processed {len(results)} notification(s)."
            )
        )
