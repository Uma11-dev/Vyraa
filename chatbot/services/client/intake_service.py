from __future__ import annotations

from chatbot.models import Client
from chatbot.services.client.client_service import ClientService


class IntakeService:

    REQUIRED_BOOKING_FIELDS = [
        "full_name",
        "email",
        "whatsapp",
        "date_of_birth",
        "birth_time",
        "birth_place",
    ]

    @staticmethod
    def get_profile_status(client: Client) -> dict:
        missing = ClientService.get_missing_profile_fields(
            client
        )

        return {
            "complete": len(missing) == 0,
            "missing": missing,
            "completed": [
                field
                for field in IntakeService.REQUIRED_BOOKING_FIELDS
                if field not in missing
            ],
        }

    @staticmethod
    def get_next_missing_field(
        client: Client,
    ) -> str | None:

        missing = ClientService.get_missing_profile_fields(
            client
        )

        if not missing:
            return None

        for field in IntakeService.REQUIRED_BOOKING_FIELDS:
            if field in missing:
                return field

        return None

    @staticmethod
    def is_ready_for_booking(
        client: Client,
    ) -> bool:

        return ClientService.is_profile_complete(
            client
        )

    @staticmethod
    def update_profile(
        client: Client,
        **kwargs,
    ) -> Client:

        allowed_fields = set(
            IntakeService.REQUIRED_BOOKING_FIELDS
        )

        clean_data = {
            key: value
            for key, value in kwargs.items()
            if key in allowed_fields
            and value is not None
        }

        if not clean_data:
            return client

        return ClientService.update_client(
            client,
            **clean_data,
        )

    @staticmethod
    def profile_summary(
        client: Client,
    ) -> dict:

        status = IntakeService.get_profile_status(
            client
        )

        return {
            "client_id": client.client_id,
            "profile_complete": status["complete"],
            "missing_fields": status["missing"],
            "profile": ClientService.to_dict(client),
        }