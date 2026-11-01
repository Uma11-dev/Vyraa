from django.utils import timezone

from .models import ChatSession, ChatMessage


class SessionService:
    """
    Handles VYRA conversation sessions and messages.
    """

    @staticmethod
    def get_or_create_session(
        session_id: str,
        client=None,
    ) -> ChatSession:

        session, created = ChatSession.objects.get_or_create(
            session_id=session_id,
            defaults={
                "client": client,
            },
        )

        # Make sure an existing session is associated
        # with the correct client.
        if client is not None and session.client_id != client.id:
            session.client = client
            session.save(update_fields=["client"])

        if created:
            print(f"[SESSION] Created: {session_id}")
        else:
            print(f"[SESSION] Resumed: {session_id}")

        return session

    @staticmethod
    def save_message(
        session: ChatSession,
        role: str,
        content: str,
    ) -> ChatMessage:

        message = ChatMessage.objects.create(
            session=session,
            role=role,
            content=content,
        )

        session.updated_at = timezone.now()
        session.save(update_fields=["updated_at"])

        print(f"[SESSION] Saved {role} message")

        return message

    @staticmethod
    def get_messages(
        session: ChatSession,
    ):
        return ChatMessage.objects.filter(
            session=session
        ).order_by("created_at")

    @staticmethod
    def get_recent_messages(
        session: ChatSession,
        limit: int = 20,
    ):
        """
        Return the most recent messages.

        Messages are returned chronologically.
        """

        messages = list(
            ChatMessage.objects.filter(
                session=session
            )
            .order_by("-created_at")[:limit]
        )

        messages.reverse()

        return messages

    @staticmethod
    def close_session(
        session: ChatSession,
    ):

        session.is_active = False

        session.save(
            update_fields=["is_active"]
        )

        print(
            f"[SESSION] Closed: "
            f"{session.session_id}"
        )