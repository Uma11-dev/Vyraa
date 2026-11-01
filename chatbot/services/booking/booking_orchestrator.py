from __future__ import annotations

from datetime import datetime

from chatbot.services.booking.availability_service import (
    AvailabilityService,
)
from chatbot.services.booking.booking_service import (
    BookingService,
)
from chatbot.services.client.client_service import (
    ClientService,
)


class BookingOrchestrator:
    """
    Coordinates the VYRA booking flow.

    This layer does not decide what service the client needs.
    ServiceRecommendationService handles that.

    This layer handles:

        profile
          ↓
        availability
          ↓
        slot validation
          ↓
        booking creation
    """

    # =========================================================
    # BOOKING READINESS
    # =========================================================

    @staticmethod
    def get_booking_readiness(client) -> dict:
        """
        Determine whether the client has supplied all
        information required to book.
        """

        missing = ClientService.get_missing_profile_fields(
            client
        )

        return {
            "ready": len(missing) == 0,
            "missing_fields": missing,
        }

    # =========================================================
    # AVAILABLE SLOTS
    # =========================================================

    @staticmethod
    def get_available_slots(
        client,
        service: str,
        days: int = 14,
    ) -> dict:
        """
        Return available slots for a specific service.

        Profile completeness is checked before availability
        is returned.

        AvailabilityService is responsible for generating
        service-duration-aware slots and checking conflicts.
        """

        readiness = (
            BookingOrchestrator
            .get_booking_readiness(client)
        )

        if not readiness["ready"]:
            return {
                "success": False,
                "reason": "profile_incomplete",
                "missing_fields": readiness[
                    "missing_fields"
                ],
                "slots": [],
            }

        service_value = (
            BookingService.normalize_service(
                service
            )
        )

        service_duration = (
            BookingService.get_service_duration(
                service_value
            )
        )

        slots = (
            AvailabilityService
            .get_available_slots(
                service=service_value,
                days=days,
            )
        )

        return {
            "success": True,
            "service": service_value,
            "service_duration_minutes": (
                service_duration
            ),
            "slots": slots,
        }

    # =========================================================
    # SLOT VALIDATION
    # =========================================================

    @staticmethod
    def validate_selected_slot(
        service: str,
        scheduled_at: datetime,
    ) -> dict:
        """
        Perform a final availability check immediately
        before creating a booking.
        """

        service_value = (
            BookingService.normalize_service(
                service
            )
        )

        available = (
            AvailabilityService
            .is_slot_available(
                scheduled_at=scheduled_at,
                service=service_value,
            )
        )

        if not available:
            return {
                "available": False,
                "service": service_value,
                "scheduled_at": scheduled_at,
                "message": (
                    "That appointment time is no "
                    "longer available."
                ),
            }

        return {
            "available": True,
            "service": service_value,
            "scheduled_at": scheduled_at,
        }

    # =========================================================
    # CREATE BOOKING
    # =========================================================

    @staticmethod
    def create_booking(
        client,
        service: str,
        scheduled_at: datetime,
        session=None,
        notes: str = "",
    ) -> dict:
        """
        Final booking operation.

        The slot is checked one final time immediately
        before BookingService creates the booking.
        """

        readiness = (
            BookingOrchestrator
            .get_booking_readiness(client)
        )

        if not readiness["ready"]:
            return {
                "success": False,
                "reason": "profile_incomplete",
                "missing_fields": readiness[
                    "missing_fields"
                ],
            }

        validation = (
            BookingOrchestrator
            .validate_selected_slot(
                service=service,
                scheduled_at=scheduled_at,
            )
        )

        if not validation["available"]:
            return {
                "success": False,
                "reason": "slot_unavailable",
                "message": validation["message"],
            }

        try:
            booking = (
                BookingService.create_booking(
                    client=client,
                    service=service,
                    scheduled_at=scheduled_at,
                    session=session,
                    notes=notes,
                )
            )

        except ValueError as exc:
            return {
                "success": False,
                "reason": "booking_failed",
                "message": str(exc),
            }

        return {
            "success": True,
            "booking": (
                BookingService.to_dict(
                    booking
                )
            ),
        }

    # =========================================================
    # FORMAT AVAILABLE SLOTS
    # =========================================================

    @staticmethod
    def format_available_slots(
        slots: list[datetime],
    ) -> list[str]:
        """
        Convert available slots into text suitable
        for VYRA.
        """

        return (
            AvailabilityService
            .format_slots(slots)
        )