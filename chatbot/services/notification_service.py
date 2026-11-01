
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from chatbot.models import Notification


class NotificationService:
    """Queue and deliver VYRA email notifications."""

    @staticmethod
    def queue_email(
        *,
        client,
        notification_type,
        subject,
        message,
        idempotency_key,
        booking=None,
        scheduled_for=None,
    ):
        if not client.email:
            return {
                "success": False,
                "reason": "Client has no email address.",
            }

        notification, created = Notification.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "client": client,
                "booking": booking,
                "notification_type": notification_type,
                "channel": "email",
                "recipient": client.email,
                "subject": subject,
                "message": message,
                "scheduled_for": scheduled_for or timezone.now(),
                "status": "pending",
            },
        )

        return {
            "success": True,
            "created": created,
            "notification_id": notification.pk,
            "status": notification.status,
        }

    @staticmethod
    def deliver(notification):
        """Attempt delivery of one pending email."""
        if notification.status != "pending":
            return {
                "success": False,
                "reason": "Notification is not pending.",
            }

        if notification.channel != "email":
            return {
                "success": False,
                "reason": "Only email delivery is implemented.",
            }

        notification.attempts += 1
        message_id = None

        try:
            if getattr(settings, "VYRA_EMAIL_PROVIDER", "django") == "gmail_api":
                from chatbot.services.gmail_service import send_gmail_email

                message_id = send_gmail_email(
                    recipient=notification.recipient,
                    subject=notification.subject,
                    message=notification.message,
                )
            else:
                sent_count = send_mail(
                    subject=notification.subject,
                    message=notification.message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[notification.recipient],
                    fail_silently=False,
                )

                if sent_count != 1:
                    raise RuntimeError(
                        "Email backend did not report a successful send."
                    )

            notification.status = "sent"
            notification.sent_at = timezone.now()
            notification.error_message = ""

        except Exception as exc:
            notification.status = "failed"
            notification.error_message = str(exc)[:2000]

        notification.save(
            update_fields=[
                "attempts",
                "status",
                "sent_at",
                "error_message",
                "updated_at",
            ]
        )

        return {
            "success": notification.status == "sent",
            "notification_id": notification.pk,
            "status": notification.status,
            "error": notification.error_message,
            "message_id": message_id,
        }

    @classmethod
    def process_due(cls, limit=100):
        """Deliver due pending notifications."""
        due_notifications = Notification.objects.filter(
            status="pending",
            scheduled_for__lte=timezone.now(),
            channel="email",
        ).order_by("scheduled_for", "created_at")[:limit]

        return [
            cls.deliver(notification)
            for notification in due_notifications
        ]
