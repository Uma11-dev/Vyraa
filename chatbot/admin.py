
from django.contrib import admin

from chatbot.models import HandoffRequest, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "notification_type",
        "channel",
        "client",
        "status",
        "attempts",
        "scheduled_for",
        "sent_at",
    )

    list_filter = (
        "notification_type",
        "channel",
        "status",
    )

    search_fields = (
        "recipient",
        "client__full_name",
        "client__email",
        "idempotency_key",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "sent_at",
        "attempts",
        "error_message",
    )


@admin.register(HandoffRequest)
class HandoffRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "reason",
        "priority",
        "status",
        "assigned_to",
        "created_at",
    )

    list_filter = (
        "status",
        "priority",
        "reason",
    )

    search_fields = (
        "client__full_name",
        "client__email",
        "summary",
        "assigned_to",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "resolved_at",
    )
