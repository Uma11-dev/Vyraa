
from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from chatbot.services.booking.booking_orchestrator import (
    BookingOrchestrator,
)
from chatbot.services.client.client_service import ClientService
from chatbot.session_service import SessionService


class ClientProfileAPIView(APIView):
    """Create or update the visitor's booking profile."""

    def post(self, request):
        client_id = str(request.data.get("client_id", "")).strip()

        if not client_id:
            return Response(
                {"success": False, "error": "client_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_name = str(request.data.get("full_name", "")).strip()
        email = str(request.data.get("email", "")).strip()
        whatsapp = str(request.data.get("whatsapp", "")).strip()
        birth_place = str(request.data.get("birth_place", "")).strip()
        birth_date_value = request.data.get("date_of_birth")
        birth_time_value = request.data.get("birth_time")

        if not all(
            [
                full_name,
                email,
                whatsapp,
                birth_date_value,
                birth_time_value,
                birth_place,
            ]
        ):
            return Response(
                {
                    "success": False,
                    "error": "Please complete all required profile fields.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_of_birth = parse_date(str(birth_date_value))
        birth_time = parse_time(str(birth_time_value))

        if date_of_birth is None:
            return Response(
                {
                    "success": False,
                    "error": "date_of_birth must be a valid YYYY-MM-DD date.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if date_of_birth > timezone.localdate():
            return Response(
                {
                    "success": False,
                    "error": "Date of birth cannot be in the future.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if birth_time is None:
            return Response(
                {
                    "success": False,
                    "error": "birth_time must be a valid HH:MM time.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            return Response(
                {
                    "success": False,
                    "error": "Please provide a valid email address.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client, _ = ClientService.get_or_create_client(client_id)

        client = ClientService.update_client(
            client,
            full_name=full_name,
            email=email,
            whatsapp=whatsapp,
            date_of_birth=date_of_birth,
            birth_time=birth_time,
            birth_place=birth_place,
        )

        return Response(
            {
                "success": True,
                "profile": ClientService.to_dict(client),
            },
            status=status.HTTP_200_OK,
        )


class BookingAvailabilityAPIView(APIView):
    """Return real, selectable appointment slots for the booking form."""

    def post(self, request):
        client_id = str(request.data.get("client_id", "")).strip()
        service = str(request.data.get("service", "")).strip()
        days_value = request.data.get("days", 60)

        if not client_id or not service:
            return Response(
                {
                    "success": False,
                    "error": "client_id and service are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            days = int(days_value)
        except (TypeError, ValueError):
            return Response(
                {
                    "success": False,
                    "error": "days must be an integer.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not 1 <= days <= 60:
            return Response(
                {
                    "success": False,
                    "error": "days must be between 1 and 60.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = ClientService.get_client(client_id)

        if client is None:
            return Response(
                {
                    "success": False,
                    "error": "Please save your profile before checking availability.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            result = BookingOrchestrator.get_available_slots(
                client=client,
                service=service,
                days=days,
            )
        except ValueError as exc:
            return Response(
                {"success": False, "error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not result.get("success"):
            return Response(
                {
                    "success": False,
                    "reason": result.get("reason"),
                    "error": (
                        "Please complete your profile before checking availability."
                        if result.get("reason") == "profile_incomplete"
                        else "Could not retrieve availability."
                    ),
                    "missing_fields": result.get("missing_fields", []),
                    "slot_options": [],
                    "slots": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_slots = result.get("slots", [])
        labels = BookingOrchestrator.format_available_slots(raw_slots)

        slot_options = [
            {
                "scheduled_at": slot.isoformat(),
                "label": labels[index]
                if index < len(labels)
                else timezone.localtime(slot).strftime("%A, %d %B at %I:%M %p"),
            }
            for index, slot in enumerate(raw_slots)
            if slot is not None
        ]

        return Response(
            {
                "success": True,
                "service": result.get("service", service),
                "service_duration_minutes": result.get(
                    "service_duration_minutes"
                ),
                "slot_options": slot_options,
                # Keep the formatted list for compatibility with older clients.
                "slots": [option["label"] for option in slot_options],
            },
            status=status.HTTP_200_OK,
        )


class BookingCreateAPIView(APIView):
    """Validate and submit a booking request."""

    def post(self, request):
        client_id = str(request.data.get("client_id", "")).strip()
        service = str(request.data.get("service", "")).strip()
        scheduled_at_value = request.data.get("scheduled_at")
        session_id = str(request.data.get("session_id", "")).strip()
        notes = str(request.data.get("notes", "")).strip()

        if not client_id or not service or not scheduled_at_value:
            return Response(
                {
                    "success": False,
                    "error": "client_id, service and scheduled_at are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = ClientService.get_client(client_id)

        if client is None:
            return Response(
                {
                    "success": False,
                    "error": "Client not found. Please save your profile first.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            scheduled_at = datetime.fromisoformat(
                str(scheduled_at_value).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            return Response(
                {
                    "success": False,
                    "error": "scheduled_at must be a valid ISO 8601 datetime.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if timezone.is_naive(scheduled_at):
            return Response(
                {
                    "success": False,
                    "error": "Appointment time must include a timezone.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = None

        if session_id:
            session = SessionService.get_or_create_session(
                session_id=session_id,
                client=client,
            )

        try:
            result = BookingOrchestrator.create_booking(
                client=client,
                service=service,
                scheduled_at=scheduled_at,
                session=session,
                notes=notes,
            )
        except ValueError as exc:
            return Response(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not result.get("success"):
            reason = result.get("reason", "booking_failed")
            message = result.get("message")

            if reason == "slot_unavailable":
                message = (
                    message
                    or "That appointment time is no longer available. "
                    "Please choose another slot."
                )
            elif reason == "profile_incomplete":
                message = (
                    "Your profile is incomplete. Please return to your details."
                )
            else:
                message = message or "The booking request could not be created."

            return Response(
                {
                    **result,
                    "success": False,
                    "error": message,
                },
                status=status.HTTP_409_CONFLICT
                if reason == "slot_unavailable"
                else status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            result,
            status=status.HTTP_201_CREATED,
        )
