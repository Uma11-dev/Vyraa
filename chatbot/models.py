
from django.db import models


# ============================================================
# CLIENT
# ============================================================

class Client(models.Model):
    """Persistent identity/profile for a VYRA client."""

    client_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
    )

    full_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    email = models.EmailField(
        blank=True,
        default="",
    )

    whatsapp = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    birth_time = models.TimeField(
        null=True,
        blank=True,
    )

    birth_place = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.full_name or self.client_id


# ============================================================
# CHAT SESSION
# ============================================================

class ChatSession(models.Model):
    """Represents one VYRA conversation session."""

    session_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    title = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    is_active = models.BooleanField(
        default=True,
    )

    # Persistent state for multi-turn booking conversations.
    # Example: {"state": "selecting_slot", "service": "future_fragments"}
    booking_state = models.JSONField(
        default=dict,
        blank=True,
    )

    def __str__(self):
        return self.session_id


# ============================================================
# CHAT MESSAGE
# ============================================================

class ChatMessage(models.Model):
    """Individual message inside a VYRA session."""

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
    )

    content = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role} - {self.session.session_id}"


# ============================================================
# SEMANTIC MEMORY
# ============================================================

class SemanticMemory(models.Model):
    """
    Durable knowledge VYRA has learned about a client.
    """

    MEMORY_TYPES = [
        ("preference", "Preference"),
        ("interest", "Interest"),
        ("goal", "Goal"),
        ("context", "Context"),
        ("service", "Service"),
        ("important", "Important"),
        ("other", "Other"),
    ]

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="semantic_memories",
    )

    memory_type = models.CharField(
        max_length=30,
        choices=MEMORY_TYPES,
    )

    content = models.TextField()

    confidence = models.FloatField(
        default=1.0,
    )

    importance = models.FloatField(
        default=0.5,
    )

    reinforcement_count = models.PositiveIntegerField(
        default=1,
    )

    last_reinforced_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    source_session = models.ForeignKey(
        ChatSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="semantic_memories",
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-importance", "-updated_at"]

    def __str__(self):
        return (
            f"{self.client} - {self.memory_type}: "
            f"{self.content[:60]}"
        )


# ============================================================
# EPISODIC MEMORY
# ============================================================

class EpisodicMemory(models.Model):
    """
    Represents a meaningful event or conversation involving a client.
    """

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="episodic_memories",
    )

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="episodes",
    )

    summary = models.TextField()

    topics = models.JSONField(
        default=list,
        blank=True,
    )

    outcome = models.TextField(
        blank=True,
        default="",
    )

    importance = models.FloatField(
        default=0.5,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    occurred_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.client} - {self.summary[:70]}"


# ============================================================
# BOOKING
# ============================================================

class Booking(models.Model):
    """Represents a Luna's Sanctum service booking."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
        ("completed", "Completed"),
    ]

    SERVICE_CHOICES = [
        ("future_fragments", "Future Fragments"),
        ("unseen_alignment", "Unseen Alignment"),
        ("karmic_pattern_mapping", "Karmic Pattern Mapping"),
    ]

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="bookings",
    )

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )

    service = models.CharField(
        max_length=100,
        choices=SERVICE_CHOICES,
    )

    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    notes = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"{self.client} - "
            f"{self.get_service_display()} - "
            f"{self.status}"
        )

# ============================================================
# NOTIFICATION
# ============================================================

class Notification(models.Model):
    """Tracks booking notifications and appointment reminders."""

    TYPE_CHOICES = [
        ("booking_requested", "Booking Requested"),
        ("booking_confirmed", "Booking Confirmed"),
        ("booking_cancelled", "Booking Cancelled"),
        ("reminder_24h", "24-Hour Reminder"),
        ("reminder_3h", "3-Hour Reminder"),
        ("handoff_created", "Human Handoff Created"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
    ]

    booking = models.ForeignKey(
        "Booking",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )

    client = models.ForeignKey(
        "Client",
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=40,
        choices=TYPE_CHOICES,
    )

    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default="email",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    recipient = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    attempts = models.PositiveIntegerField(default=0)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_for", "created_at"]

    def __str__(self):
        return (
            f"{self.notification_type} | "
            f"{self.client} | {self.status}"
        )


# ============================================================
# HUMAN HANDOFF
# ============================================================

class HandoffRequest(models.Model):
    """A persistent request for human assistance from Uma."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("assigned", "Assigned"),
        ("resolved", "Resolved"),
        ("cancelled", "Cancelled"),
    ]

    PRIORITY_CHOICES = [
        ("normal", "Normal"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    REASON_CHOICES = [
        ("client_requested", "Client Requested"),
        ("booking_issue", "Booking Issue"),
        ("custom_request", "Custom Request"),
        ("complaint", "Complaint"),
        ("sensitive_topic", "Sensitive Topic"),
        ("assistant_limit", "Assistant Limitation"),
        ("other", "Other"),
    ]

    client = models.ForeignKey(
        "Client",
        on_delete=models.CASCADE,
        related_name="handoff_requests",
    )

    session = models.ForeignKey(
        "ChatSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handoff_requests",
    )

    reason = models.CharField(
        max_length=40,
        choices=REASON_CHOICES,
        default="client_requested",
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="normal",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
    )

    summary = models.TextField()
    assigned_to = models.CharField(max_length=255, blank=True)
    resolution_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Handoff #{self.pk} | "
            f"{self.client} | {self.status}"
        )
