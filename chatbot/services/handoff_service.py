
from django.db import transaction
from django.utils import timezone

from chatbot.models import HandoffRequest, Notification
from chatbot.services.notification_service import NotificationService


class HandoffService:
    """Create and manage persistent requests for human assistance."""

    @staticmethod
    @transaction.atomic
    def create(
        *,
        client,
        session=None,
        summary,
        reason="client_requested",
        priority="normal",
    ):
        handoff = HandoffRequest.objects.create(
            client=client,
            session=session,
            summary=summary,
            reason=reason,
            priority=priority,
        )

        # Notify the client that the request has been recorded.
        NotificationService.queue_email(
            client=client,
            notification_type="handoff_created",
            subject="Your request has been sent to Luna's Sanctum",
            message=(
                f"Hello {client.full_name or 'there'},\n\n"
                "Your request has been recorded and passed to "
                "the Luna's Sanctum team for follow-up.\n\n"
                "This message confirms receipt of your request; "
                "it does not guarantee a response time.\n\n"
                "With care,\nLuna's Sanctum"
            ),
            idempotency_key=f"handoff:{handoff.pk}:client-receipt",
            scheduled_for=timezone.now(),
        )

        return handoff

    @staticmethod
    def assign(handoff, assigned_to):
        handoff.assigned_to = assigned_to
        handoff.status = "assigned"
        handoff.save(
            update_fields=[
                "assigned_to",
                "status",
                "updated_at",
            ]
        )
        return handoff

    @staticmethod
    def resolve(handoff, resolution_notes=""):
        handoff.status = "resolved"
        handoff.resolution_notes = resolution_notes
        handoff.resolved_at = timezone.now()
        handoff.save(
            update_fields=[
                "status",
                "resolution_notes",
                "resolved_at",
                "updated_at",
            ]
        )
        return handoff
