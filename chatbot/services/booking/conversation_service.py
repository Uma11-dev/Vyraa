
from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from chatbot.services.booking.booking_orchestrator import (
    BookingOrchestrator,
)
from chatbot.services.booking.booking_service import BookingService
from chatbot.services.client.client_service import ClientService


class BookingConversationService:
    """
    Deterministic booking workflow for VYRA.

    This service handles booking operations only. It does not
    generate natural-language responses or perform readings.

    Workflow:
        service selection
        -> profile completion
        -> availability
        -> slot selection
        -> explicit confirmation
        -> pending booking
    """

    REQUIRED_PROFILE_FIELDS = (
        "full_name",
        "email",
        "whatsapp",
        "date_of_birth",
        "birth_time",
        "birth_place",
    )

    @staticmethod
    def start(client, service: str) -> dict:
        """Start booking a supported service."""

        normalized_service = BookingService.normalize_service(service)

        readiness = BookingOrchestrator.get_booking_readiness(client)

        if not readiness["ready"]:
            return {
                "success": True,
                "state": "collecting_profile",
                "service": normalized_service,
                "missing_fields": readiness["missing_fields"],
                "message": (
                    "Before we look at appointment times, "
                    "I need a few details to complete your client profile."
                ),
            }

        return {
            "success": True,
            "state": "selecting_slot",
            "service": normalized_service,
            "message": (
                "Your profile is complete. Let's look at available "
                "appointment times."
            ),
        }

    @staticmethod
    def get_slots(client, service: str, days: int = 14) -> dict:
        """Return real available slots after profile completion."""

        result = BookingOrchestrator.get_available_slots(
            client=client,
            service=service,
            days=days,
        )

        if not result["success"]:
            return {
                "success": False,
                "state": "collecting_profile",
                "missing_fields": result.get("missing_fields", []),
                "slots": [],
                "message": (
                    "Please complete your client profile before "
                    "checking appointment availability."
                ),
            }

        slots = result.get("slots", [])

        return {
            "success": True,
            "state": "selecting_slot",
            "service": result["service"],
            "service_duration_minutes": result[
                "service_duration_minutes"
            ],
            "slots": [
                {
                    "scheduled_at": slot.isoformat(),
                    "label": timezone.localtime(slot).strftime(
                        "%A, %d %B %Y at %I:%M %p"
                    ),
                }
                for slot in slots
            ],
            "message": (
                "Here are the available appointment times."
                if slots
                else "There are no available slots in this period."
            ),
        }

    @staticmethod
    def prepare_confirmation(
        client,
        service: str,
        scheduled_at: str | datetime,
    ) -> dict:
        """
        Validate a requested slot without creating a booking.

        The caller must retain the returned canonical datetime and
        obtain explicit client confirmation before calling confirm().
        """

        normalized_service = BookingService.normalize_service(service)

        if isinstance(scheduled_at, str):
            try:
                scheduled_at = datetime.fromisoformat(
                    scheduled_at.replace("Z", "+00:00")
                )
            except ValueError:
                return {
                    "success": False,
                    "state": "selecting_slot",
                    "message": "Please choose a valid appointment time.",
                }

        if timezone.is_naive(scheduled_at):
            return {
                "success": False,
                "state": "selecting_slot",
                "message": (
                    "The appointment time must include a timezone. "
                    "Please select one of the available slots."
                ),
            }

        readiness = BookingOrchestrator.get_booking_readiness(client)

        if not readiness["ready"]:
            return {
                "success": False,
                "state": "collecting_profile",
                "missing_fields": readiness["missing_fields"],
                "message": "Please complete your client profile first.",
            }

        validation = BookingOrchestrator.validate_selected_slot(
            service=normalized_service,
            scheduled_at=scheduled_at,
        )

        if not validation["available"]:
            return {
                "success": False,
                "state": "selecting_slot",
                "message": validation["message"],
            }

        return {
            "success": True,
            "state": "awaiting_confirmation",
            "service": normalized_service,
            "scheduled_at": scheduled_at.isoformat(),
            "message": (
                "This appointment time is available. "
                "Would you like me to create this booking?"
            ),
        }

    @staticmethod
    def confirm(
        client,
        service: str,
        scheduled_at: str | datetime,
        session=None,
        notes: str = "",
    ) -> dict:
        """
        Create a pending booking after the caller has obtained
        explicit confirmation from the client.

        IMPORTANT: This method must only be called by trusted
        application logic after explicit confirmation. It does not
        interpret a natural-language yes/no message itself.
        """

        if isinstance(scheduled_at, str):
            try:
                scheduled_at = datetime.fromisoformat(
                    scheduled_at.replace("Z", "+00:00")
                )
            except ValueError:
                return {
                    "success": False,
                    "state": "selecting_slot",
                    "message": "Please choose a valid appointment time.",
                }

        if timezone.is_naive(scheduled_at):
            return {
                "success": False,
                "state": "selecting_slot",
                "message": "The appointment time must include a timezone.",
            }

        result = BookingOrchestrator.create_booking(
            client=client,
            service=service,
            scheduled_at=scheduled_at,
            session=session,
            notes=notes,
        )

        if not result["success"]:
            return {
                **result,
                "state": (
                    "collecting_profile"
                    if result.get("reason") == "profile_incomplete"
                    else "selecting_slot"
                ),
            }

        return {
            "success": True,
            "state": "booking_created",
            "booking": result["booking"],
            "message": (
                "Your booking has been created and is pending confirmation. "
                "It is not yet confirmed."
            ),
        }
