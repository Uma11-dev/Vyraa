
from __future__ import annotations

from datetime import timedelta

from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from chatbot.models import Booking, ChatSession, Client
from chatbot.services.notification_service import NotificationService
from datetime import date, datetime, time
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


class BookingService:
    """
    Booking business logic for VYRA.

    Handles service validation, client validation, minimum booking notice,
    interval calculations, conflict checks, lifecycle operations,
    notification queueing, and API-safe serialization.

    Availability generation is handled by AvailabilityService.
    """

    MINIMUM_NOTICE_DAYS = 3

    SERVICE_MAP = {
        "Future Fragments": "future_fragments",
        "Unseen Alignment": "unseen_alignment",
        "Karmic Pattern Mapping": "karmic_pattern_mapping",
    }

    SERVICE_DURATIONS = {
        "future_fragments": 60,
        "unseen_alignment": 75,
        "karmic_pattern_mapping": 90,
    }

    ACTIVE_STATUSES = ("pending", "confirmed")

    # =========================================================
    # SERVICE
    # =========================================================

    @staticmethod
    def normalize_service(service: str) -> str:
        """Convert a supported service name or key to its database value."""
        if not isinstance(service, str) or not service.strip():
            raise ValueError("Service is required.")

        service = service.strip()

        if service in BookingService.SERVICE_MAP:
            return BookingService.SERVICE_MAP[service]

        normalized = service.lower().replace("-", "_").replace(" ", "_")

        if normalized not in BookingService.SERVICE_DURATIONS:
            raise ValueError(f"Invalid Luna's Sanctum service: {service}")

        return normalized

    @staticmethod
    def get_service_duration(service: str) -> int:
        """Return a service's duration in minutes."""
        service_value = BookingService.normalize_service(service)
        return BookingService.SERVICE_DURATIONS[service_value]

    # =========================================================
    # CLIENT
    # =========================================================

    @staticmethod
    def validate_client(client: Client) -> Client:
        """Ensure the client object has a usable client ID."""
        if client is None or not getattr(client, "client_id", None):
            raise ValueError("A valid client is required.")

        return client

    # =========================================================
    # BOOKING TIME
    # =========================================================

    @staticmethod
    def validate_booking_time(scheduled_at):
        """Validate a booking datetime and enforce minimum notice."""
        if scheduled_at is None:
            raise ValueError("A booking date and time are required.")

        if timezone.is_naive(scheduled_at):
            raise ValueError(
                "The booking date and time must include a timezone."
            )

        minimum_time = timezone.now() + timedelta(
            days=BookingService.MINIMUM_NOTICE_DAYS
        )

        if scheduled_at < minimum_time:
            raise ValueError(
                "Luna's Sanctum requires at least "
                f"{BookingService.MINIMUM_NOTICE_DAYS} days notice for bookings."
            )

        return scheduled_at

    # =========================================================
    # BOOKING INTERVAL
    # =========================================================

    @staticmethod
    def get_booking_end(scheduled_at, service: str):
        """Calculate the end time using the selected service duration."""
        return scheduled_at + timedelta(
            minutes=BookingService.get_service_duration(service)
        )

    # =========================================================
    # CONFLICT DETECTION
    # =========================================================

    @staticmethod
    def has_conflicting_booking(
        scheduled_at,
        service: str,
        exclude_booking_id=None,
    ) -> bool:
        """Return True when an active booking overlaps this interval."""
        service_value = BookingService.normalize_service(service)

        new_start = scheduled_at
        new_end = BookingService.get_booking_end(
            scheduled_at=scheduled_at,
            service=service_value,
        )

        bookings = Booking.objects.filter(
            status__in=BookingService.ACTIVE_STATUSES,
            scheduled_at__isnull=False,
        )

        if exclude_booking_id is not None:
            bookings = bookings.exclude(pk=exclude_booking_id)

        for booking in bookings.iterator():
            existing_start = booking.scheduled_at
            existing_end = BookingService.get_booking_end(
                scheduled_at=existing_start,
                service=booking.service,
            )

            if new_start < existing_end and new_end > existing_start:
                return True

        return False

    # =========================================================
    # TRANSACTION LOCK
    # =========================================================

    @staticmethod
    def _acquire_booking_write_lock(client: Client) -> None:
        """
        Acquire SQLite's database write lock before checking conflicts.

        A no-op UPDATE starts a write operation without changing client data.
        Other database engines use their normal transaction behavior here;
        this method does not provide a cross-database advisory lock.
        """
        if connection.vendor != "sqlite":
            return

        updated = Client.objects.filter(pk=client.pk).update(
            client_id=F("client_id")
        )

        if not updated:
            raise ValueError("The client no longer exists.")

    # =========================================================
    # NOTIFICATIONS
    # =========================================================

    @staticmethod
    def _queue_booking_email(
        booking: Booking,
        notification_type: str,
        subject: str,
        message: str,
    ) -> None:
        """
        Queue a lifecycle email.

        This creates a notification record; it does not send the email
        immediately. Delivery is handled by NotificationService.
        """
        if booking.scheduled_at is not None:
            appointment_time = timezone.localtime(
                booking.scheduled_at
            ).strftime("%A, %d %B %Y at %I:%M %p IST")
        else:
            appointment_time = "To be scheduled"

        message = message.format(
            client_name=booking.client.full_name or "there",
            service=booking.get_service_display(),
            appointment_time=appointment_time,
            duration=BookingService.get_service_duration(booking.service),
            booking_id=booking.pk,
        )

        NotificationService.queue_email(
            client=booking.client,
            booking=booking,
            notification_type=notification_type,
            subject=subject.format(
                service=booking.get_service_display(),
                booking_id=booking.pk,
            ),
            message=message,
            idempotency_key=f"booking:{booking.pk}:{notification_type}",
        )

    # =========================================================
    # CREATE
    # =========================================================

    @staticmethod
    def create_booking(
        client: Client,
        service: str,
        scheduled_at,
        session: ChatSession | None = None,
        notes: str = "",
    ) -> Booking:
        """Create a pending booking after validating the requested slot."""
        client = BookingService.validate_client(client)
        service_value = BookingService.normalize_service(service)
        scheduled_at = BookingService.validate_booking_time(scheduled_at)

        with transaction.atomic():
            # On SQLite, acquire the write lock before the conflict read.
            BookingService._acquire_booking_write_lock(client)

            if BookingService.has_conflicting_booking(
                scheduled_at=scheduled_at,
                service=service_value,
            ):
                raise ValueError(
                    "This time overlaps with another existing booking."
                )

            booking = Booking.objects.create(
                client=client,
                session=session,
                service=service_value,
                scheduled_at=scheduled_at,
                status="pending",
                notes=(notes or "").strip(),
            )

            # Queue inside the transaction so the booking and its
            # notification record are committed together.
            BookingService._queue_booking_email(
                booking=booking,
                notification_type="booking_requested",
                subject="Booking request received — {service}",
                message=(
                    "Hello {client_name},\n\n"
                    "VYRA has received your booking request for {service}.\n\n"
                    "Requested appointment: {appointment_time}\n"
                    "Duration: {duration} minutes\n"
                    "Reference: {booking_id}\n\n"
                    "Your booking is currently PENDING and is not yet "
                    "confirmed. We will notify you when its status changes.\n\n"
                    "Luna's Sanctum"
                ),
            )

        print(
            "[BOOKING] Created:",
            booking.id,
            booking.get_service_display(),
            scheduled_at,
        )
        return booking

    # =========================================================
    # RETRIEVE CLIENT BOOKINGS
    # =========================================================

    @staticmethod
    def get_client_bookings(
        client: Client,
        include_cancelled: bool = False,
    ) -> list[Booking]:
        """Return a client's bookings, newest scheduled first."""
        client = BookingService.validate_client(client)

        query = Booking.objects.filter(client=client).order_by("-scheduled_at")

        if not include_cancelled:
            query = query.exclude(status="cancelled")

        return list(query)

    # =========================================================
    # GET SINGLE BOOKING
    # =========================================================

    @staticmethod
    def get_booking(
        booking_id: int,
        client: Client | None = None,
    ) -> Booking | None:
        """Retrieve a booking, optionally restricting it to a client."""
        query = Booking.objects.filter(pk=booking_id)

        if client is not None:
            query = query.filter(client=client)

        return query.first()

    # =========================================================
    # CONFIRM
    # =========================================================

    @staticmethod
    def confirm_booking(booking: Booking) -> Booking:
        """Confirm a pending booking after rechecking for conflicts."""
        with transaction.atomic():
            if connection.vendor == "sqlite":
                # Acquire the SQLite write lock before the conflict check.
                BookingService._acquire_booking_write_lock(booking.client)

            booking = Booking.objects.get(pk=booking.pk)

            if booking.status != "pending":
                raise ValueError("Only pending bookings can be confirmed.")

            if booking.scheduled_at is None:
                raise ValueError(
                    "Cannot confirm a booking without a scheduled date and time."
                )

            # The three-day notice rule applies when a booking is created.
            # Do not reapply it during confirmation.
            if BookingService.has_conflicting_booking(
                scheduled_at=booking.scheduled_at,
                service=booking.service,
                exclude_booking_id=booking.pk,
            ):
                raise ValueError(
                    "Another booking now overlaps with this appointment."
                )

            booking.status = "confirmed"
            booking.save(update_fields=["status", "updated_at"])

            BookingService._queue_booking_email(
                booking=booking,
                notification_type="booking_confirmed",
                subject="Booking confirmed — {service}",
                message=(
                    "Hello {client_name},\n\n"
                    "Your booking with Luna's Sanctum has been confirmed.\n\n"
                    "Service: {service}\n"
                    "Appointment: {appointment_time}\n"
                    "Duration: {duration} minutes\n"
                    "Reference: {booking_id}\n\n"
                    "Please keep this reference for your records.\n\n"
                    "Luna's Sanctum"
                ),
            )

        print("[BOOKING] Confirmed:", booking.id)
        return booking

    # =========================================================
    # CANCEL
    # =========================================================

    @staticmethod
    def cancel_booking(booking: Booking) -> Booking:
        """Cancel a booking unless it has already been completed."""
        if booking.status == "cancelled":
            return booking

        if booking.status == "completed":
            raise ValueError("A completed booking cannot be cancelled.")

        booking.status = "cancelled"
        booking.save(update_fields=["status", "updated_at"])

        BookingService._queue_booking_email(
            booking=booking,
            notification_type="booking_cancelled",
            subject="Booking cancelled — {service}",
            message=(
                "Hello {client_name},\n\n"
                "Your booking with Luna's Sanctum has been cancelled.\n\n"
                "Service: {service}\n"
                "Appointment: {appointment_time}\n"
                "Reference: {booking_id}\n\n"
                "If you did not request this cancellation or would like "
                "assistance, please contact Luna's Sanctum.\n\n"
                "Luna's Sanctum"
            ),
        )

        print("[BOOKING] Cancelled:", booking.id)
        return booking

    # =========================================================
    # COMPLETE
    # =========================================================

    @staticmethod
    def complete_booking(booking: Booking) -> Booking:
        """Mark a confirmed booking as completed."""
        if booking.status != "confirmed":
            raise ValueError("Only confirmed bookings can be completed.")

        booking.status = "completed"
        booking.save(update_fields=["status", "updated_at"])

        print("[BOOKING] Completed:", booking.id)
        return booking

    # =========================================================
    # SERIALIZATION
    # =========================================================

    @staticmethod
    def to_dict(booking: Booking) -> dict:
        """Convert a booking to a JSON-friendly dictionary."""
        duration = BookingService.get_service_duration(booking.service)
        end_time = None

        if booking.scheduled_at is not None:
            end_time = booking.scheduled_at + timedelta(minutes=duration)

        return {
            "id": booking.pk,
            "client_id": booking.client.client_id,
            "service": booking.service,
            "service_name": booking.get_service_display(),
            "duration_minutes": duration,
            "scheduled_at": (
                booking.scheduled_at.isoformat()
                if booking.scheduled_at is not None
                else None
            ),
            "ends_at": (
                end_time.isoformat()
                if end_time is not None
                else None
            ),
            "status": booking.status,
            "notes": booking.notes,
            "created_at": (
                booking.created_at.isoformat()
                if booking.created_at is not None
                else None
            ),
            "updated_at": (
                booking.updated_at.isoformat()
                if booking.updated_at is not None
                else None
            ),
        }



