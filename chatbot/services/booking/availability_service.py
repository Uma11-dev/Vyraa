from __future__ import annotations

from datetime import datetime, time, timedelta

from django.utils import timezone

from chatbot.models import Booking
from chatbot.services.booking.booking_service import BookingService


class AvailabilityService:
    """
    Determines which appointment slots are available for
    Luna's Sanctum bookings.

    Availability is calculated according to:

    - working days
    - working hours
    - minimum booking notice
    - requested service duration
    - existing pending/confirmed bookings
    - overlapping appointment protection
    """

    MINIMUM_NOTICE_DAYS = 3

    WORKING_DAYS = {
        0,  # Monday
        1,  # Tuesday
        2,  # Wednesday
        3,  # Thursday
        4,  # Friday
        5,  # Saturday
    }

    WORK_START = time(10, 0)
    WORK_END = time(20, 0)

    SLOT_INTERVAL_MINUTES = 15

    # =========================================================
    # SERVICE
    # =========================================================

    @staticmethod
    def normalize_service(service: str) -> str:
        return BookingService.normalize_service(service)

    @staticmethod
    def get_service_duration(service: str) -> int:
        return BookingService.get_service_duration(service)

    # =========================================================
    # WORKING HOURS
    # =========================================================

    @staticmethod
    def is_working_day(target_date) -> bool:
        return (
            target_date.weekday()
            in AvailabilityService.WORKING_DAYS
        )

    @staticmethod
    def get_working_window(target_date):
        """
        Return the start and end datetime for a working day.
        """

        if not AvailabilityService.is_working_day(
            target_date
        ):
            return None, None

        start = timezone.make_aware(
            datetime.combine(
                target_date,
                AvailabilityService.WORK_START,
            )
        )

        end = timezone.make_aware(
            datetime.combine(
                target_date,
                AvailabilityService.WORK_END,
            )
        )

        return start, end

    # =========================================================
    # SLOT GENERATION
    # =========================================================

    @staticmethod
    def generate_slots_for_date(
        target_date,
        service: str,
    ) -> list[datetime]:
        """
        Generate candidate appointment start times for a
        specific service.

        The service duration determines whether the appointment
        can fit completely inside the working window.
        """

        service_duration = (
            AvailabilityService.get_service_duration(
                service
            )
        )

        work_start, work_end = (
            AvailabilityService.get_working_window(
                target_date
            )
        )

        if work_start is None:
            return []

        slots = []

        current = work_start

        while (
            current
            + timedelta(minutes=service_duration)
            <= work_end
        ):
            slots.append(current)

            current += timedelta(
                minutes=(
                    AvailabilityService
                    .SLOT_INTERVAL_MINUTES
                )
            )

        return slots

    # =========================================================
    # BOOKING INTERVAL
    # =========================================================

    @staticmethod
    def get_booking_end(
        scheduled_at,
        service: str,
    ):
        duration = (
            AvailabilityService.get_service_duration(
                service
            )
        )

        return scheduled_at + timedelta(
            minutes=duration
        )

    # =========================================================
    # EXISTING BOOKINGS
    # =========================================================

    @staticmethod
    def get_existing_bookings(
        start_datetime,
        end_datetime,
    ):
        """
        Return pending and confirmed bookings that could
        overlap the requested window.
        """

        return Booking.objects.filter(
            status__in=[
                "pending",
                "confirmed",
            ],
            scheduled_at__isnull=False,
            scheduled_at__lt=end_datetime,
        ).filter(
            scheduled_at__gte=(
                start_datetime
                - timedelta(minutes=120)
            )
        )

    # =========================================================
    # OVERLAP CHECK
    # =========================================================

    @staticmethod
    def slot_overlaps_booking(
        slot_start,
        slot_end,
        booking,
    ) -> bool:
        """
        Determine whether a candidate slot overlaps
        an existing booking.
        """

        if booking.scheduled_at is None:
            return False

        booking_start = booking.scheduled_at

        booking_end = (
            AvailabilityService.get_booking_end(
                scheduled_at=booking_start,
                service=booking.service,
            )
        )

        return (
            slot_start < booking_end
            and slot_end > booking_start
        )

    # =========================================================
    # SLOT AVAILABILITY
    # =========================================================

    @staticmethod
    def is_slot_available(
        scheduled_at,
        service: str,
    ) -> bool:
        """
        Check whether a specific service can be booked
        at a specific time.
        """

        service_value = (
            AvailabilityService.normalize_service(
                service
            )
        )

        minimum_time = (
            timezone.now()
            + timedelta(
                days=AvailabilityService.MINIMUM_NOTICE_DAYS
            )
        )

        if scheduled_at < minimum_time:
            return False

        if not AvailabilityService.is_working_day(
            scheduled_at.date()
        ):
            return False

        work_start, work_end = (
            AvailabilityService.get_working_window(
                scheduled_at.date()
            )
        )

        if (
            scheduled_at < work_start
            or scheduled_at >= work_end
        ):
            return False

        slot_end = (
            AvailabilityService.get_booking_end(
                scheduled_at=scheduled_at,
                service=service_value,
            )
        )

        if slot_end > work_end:
            return False

        bookings = (
            AvailabilityService.get_existing_bookings(
                start_datetime=scheduled_at,
                end_datetime=slot_end,
            )
        )

        for booking in bookings:
            if AvailabilityService.slot_overlaps_booking(
                slot_start=scheduled_at,
                slot_end=slot_end,
                booking=booking,
            ):
                return False

        return True

    # =========================================================
    # DAILY AVAILABILITY
    # =========================================================

    @staticmethod
    def get_available_slots_for_date(
        target_date,
        service: str,
    ) -> list[datetime]:
        """
        Return available slots for a specific date and
        specific service.
        """

        candidate_slots = (
            AvailabilityService.generate_slots_for_date(
                target_date=target_date,
                service=service,
            )
        )

        return [
            slot
            for slot in candidate_slots
            if AvailabilityService.is_slot_available(
                scheduled_at=slot,
                service=service,
            )
        ]

    # =========================================================
    # MULTI-DAY AVAILABILITY
    # =========================================================

    @staticmethod
    def get_available_slots(
        service: str,
        start_date=None,
        days: int = 14,
    ) -> list[datetime]:
        """
        Return available slots for a specific service
        across a range of dates.
        """

        service_value = (
            AvailabilityService.normalize_service(
                service
            )
        )

        if start_date is None:
            start_date = timezone.localdate()

        available_slots = []

        for offset in range(days):
            target_date = (
                start_date
                + timedelta(days=offset)
            )

            daily_slots = (
                AvailabilityService
                .get_available_slots_for_date(
                    target_date=target_date,
                    service=service_value,
                )
            )

            available_slots.extend(
                daily_slots
            )

        return available_slots

    # =========================================================
    # FORMAT
    # =========================================================

    @staticmethod
    def format_slots(
        slots: list[datetime],
    ) -> list[str]:
        """
        Convert datetime objects into human-readable
        strings for VYRA.
        """

        return [
            slot.strftime(
                "%A, %d %B %Y at %I:%M %p"
            )
            for slot in slots
        ]