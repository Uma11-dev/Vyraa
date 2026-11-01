from __future__ import annotations

from datetime import date, time
from typing import Optional

from chatbot.models import Client


class ClientService:
    """
    Handles VYRA client profile operations.

    This service is responsible for structured client information
    such as name, contact details, and birth information.

    It does NOT handle:
    - conversations
    - long-term memories
    - bookings
    - notifications
    """

    # =========================================================
    # Get / Create
    # =========================================================

    @staticmethod
    def get_or_create_client(
        client_id: str,
    ) -> tuple[Client, bool]:
        """
        Retrieve an existing client or create a new one.

        Returns:
            (client, created)
        """

        client, created = Client.objects.get_or_create(
            client_id=client_id,
        )

        if created:
            print(
                f"[CLIENT] Created client: {client_id}"
            )
        else:
            print(
                f"[CLIENT] Loaded client: {client_id}"
            )

        return client, created

    # =========================================================
    # Get
    # =========================================================

    @staticmethod
    def get_client(
        client_id: str,
    ) -> Optional[Client]:
        """
        Retrieve a client by client_id.

        Returns None if the client does not exist.
        """

        return Client.objects.filter(
            client_id=client_id,
        ).first()

    # =========================================================
    # Update Profile
    # =========================================================

    @staticmethod
    def update_client(
        client: Client,
        *,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        whatsapp: Optional[str] = None,
        date_of_birth: Optional[date] = None,
        birth_time: Optional[time] = None,
        birth_place: Optional[str] = None,
    ) -> Client:
        """
        Update only the client fields that were supplied.
        """

        fields_to_update = []

        if full_name is not None:
            client.full_name = full_name.strip()
            fields_to_update.append("full_name")

        if email is not None:
            client.email = email.strip()
            fields_to_update.append("email")

        if whatsapp is not None:
            client.whatsapp = whatsapp.strip()
            fields_to_update.append("whatsapp")

        if date_of_birth is not None:
            client.date_of_birth = date_of_birth
            fields_to_update.append("date_of_birth")

        if birth_time is not None:
            client.birth_time = birth_time
            fields_to_update.append("birth_time")

        if birth_place is not None:
            client.birth_place = birth_place.strip()
            fields_to_update.append("birth_place")

        if fields_to_update:
            fields_to_update.append("updated_at")

            client.save(
                update_fields=fields_to_update,
            )

            print(
                f"[CLIENT] Updated: "
                f"{client.client_id}"
            )

        return client

    # =========================================================
    # Profile Completeness
    # =========================================================

    @staticmethod
    def get_missing_profile_fields(
        client: Client,
    ) -> list[str]:
        """
        Return fields that are currently missing.

        This will later allow VYRA to ask only for the
        information it actually needs.
        """

        missing = []

        if not client.full_name:
            missing.append("full_name")

        if not client.email:
            missing.append("email")

        if not client.whatsapp:
            missing.append("whatsapp")

        if not client.date_of_birth:
            missing.append("date_of_birth")

        if not client.birth_time:
            missing.append("birth_time")

        if not client.birth_place:
            missing.append("birth_place")

        return missing

    # =========================================================
    # Profile Status
    # =========================================================

    @staticmethod
    def is_profile_complete(
        client: Client,
    ) -> bool:
        """
        Determine whether all currently required client
        profile information is present.
        """

        return not ClientService.get_missing_profile_fields(
            client
        )

    # =========================================================
    # Safe Profile Representation
    # =========================================================

    @staticmethod
    def to_dict(
        client: Client,
    ) -> dict:
        """
        Convert a client profile into a dictionary suitable
        for API responses or internal processing.

        This deliberately excludes internal database fields.
        """

        return {
            "client_id": client.client_id,
            "full_name": client.full_name,
            "email": client.email,
            "whatsapp": client.whatsapp,
            "date_of_birth": (
                client.date_of_birth.isoformat()
                if client.date_of_birth
                else None
            ),
            "birth_time": (
                client.birth_time.isoformat()
                if client.birth_time
                else None
            ),
            "birth_place": client.birth_place,
        }