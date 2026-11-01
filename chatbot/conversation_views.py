from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from chatbot.models import ChatMessage, ChatSession, Client


def _client_id(value: object) -> str:
    return str(value or "").strip()


def _message_data(message: ChatMessage) -> dict:
    return {
        "id": message.pk,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def _session_data(session: ChatSession, messages: list[ChatMessage] | None = None) -> dict:
    items = messages if messages is not None else list(session.messages.all())
    user_messages = [item for item in items if item.role == "user"]
    visible_messages = [item for item in items if item.role in ("user", "assistant")]
    first_user = user_messages[0].content if user_messages else ""
    latest = visible_messages[-1].content if visible_messages else ""
    stored_title = (session.title or "").strip()
    title = stored_title if stored_title and stored_title.lower() != "new conversation" else (first_user.strip()[:64] if first_user else "New conversation")
    preview = latest.strip().replace("\n", " ")[:130] if latest else "Your conversation starts here"
    return {
        "session_id": session.session_id,
        "title": title,
        "preview": preview,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "message_count": len(items),
        "is_active": session.is_active,
    }


class ConversationSessionListCreateAPIView(APIView):
    """List a visitor's VYRA conversations or create a new conversation."""

    def get(self, request):
        client_id = _client_id(request.query_params.get("client_id"))
        if not client_id:
            return Response(
                {"error": "client_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = Client.objects.filter(client_id=client_id).first()
        if client is None:
            return Response({"sessions": []}, status=status.HTTP_200_OK)

        first_user_message = (
            ChatMessage.objects.filter(session_id=OuterRef("pk"), role="user")
            .order_by("created_at", "pk")
            .values("content")[:1]
        )
        latest_message = (
            ChatMessage.objects.filter(
                session_id=OuterRef("pk"), role__in=("user", "assistant")
            )
            .order_by("-created_at", "-pk")
            .values("content")[:1]
        )
        message_count = (
            ChatMessage.objects.filter(session_id=OuterRef("pk"))
            .order_by()
            .values("session_id")
            .annotate(total=Count("pk"))
            .values("total")[:1]
        )
        sessions = (
            ChatSession.objects.filter(client=client)
            .annotate(
                first_user_content=Subquery(first_user_message),
                latest_message_content=Subquery(latest_message),
                total_messages=Coalesce(
                    Subquery(message_count, output_field=IntegerField()), Value(0)
                ),
            )
            .order_by("-updated_at", "-created_at")[:100]
        )
        payload = []
        for session in sessions:
            stored_title = (session.title or "").strip()
            first_user = (getattr(session, "first_user_content", "") or "").strip()
            latest = (getattr(session, "latest_message_content", "") or "").strip()
            title = stored_title if stored_title and stored_title.lower() != "new conversation" else (first_user[:64] if first_user else "New conversation")
            payload.append({
                "session_id": session.session_id,
                "title": title,
                "preview": latest.replace("\n", " ")[:130] if latest else "Your conversation starts here",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "message_count": session.total_messages,
                "is_active": session.is_active,
            })

        return Response({"sessions": payload}, status=status.HTTP_200_OK)

    def post(self, request):
        client_id = _client_id(request.data.get("client_id"))
        session_id = _client_id(request.data.get("session_id"))

        if not client_id or not session_id:
            return Response(
                {"error": "client_id and session_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(client_id) > 100 or len(session_id) > 100:
            return Response(
                {"error": "client_id and session_id must not exceed 100 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client, _ = Client.objects.get_or_create(client_id=client_id)

        try:
            with transaction.atomic():
                session = ChatSession.objects.select_for_update().filter(
                    session_id=session_id
                ).first()
                if session is not None:
                    if session.client_id not in (None, client.pk):
                        return Response(
                            {"error": "This conversation does not belong to this client."},
                            status=status.HTTP_404_NOT_FOUND,
                        )
                    if session.client_id is None:
                        session.client = client
                        session.save(update_fields=["client"])
                else:
                    session = ChatSession.objects.create(
                        session_id=session_id,
                        client=client,
                        title="New conversation",
                        is_active=True,
                    )
        except IntegrityError:
            session = ChatSession.objects.filter(
                session_id=session_id,
                client=client,
            ).first()
            if session is None:
                return Response(
                    {"error": "Could not create this conversation. Please try again."},
                    status=status.HTTP_409_CONFLICT,
                )

        return Response(
            {"session": _session_data(session)},
            status=status.HTTP_201_CREATED,
        )


class ConversationMessageListAPIView(APIView):
    """Return persisted messages for a session owned by the supplied client."""

    def get(self, request, session_id: str):
        client_id = _client_id(request.query_params.get("client_id"))
        if not client_id:
            return Response(
                {"error": "client_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = Client.objects.filter(client_id=client_id).first()
        if client is None:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        session = (
            ChatSession.objects.filter(session_id=session_id, client=client)
            .first()
        )
        if session is None:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            limit = int(request.query_params.get("limit", 300))
        except (TypeError, ValueError):
            return Response(
                {"error": "limit must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if limit < 1 or limit > 500:
            return Response(
                {"error": "limit must be between 1 and 500."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message_rows = list(
            ChatMessage.objects.filter(session=session)
            .order_by("-created_at", "-id")[:limit]
        )
        message_rows.reverse()

        return Response(
            {
                "session": _session_data(session, message_rows),
                "messages": [_message_data(message) for message in message_rows],
            },
            status=status.HTTP_200_OK,
        )
