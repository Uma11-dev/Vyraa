
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from chatbot.models import (
    Client,
    ChatSession,
    SemanticMemory,
    EpisodicMemory,
)


class MemoryService:
    """Persistence operations for VYRA's hybrid memory system."""

    @staticmethod
    def attach_session_to_client(
        session: ChatSession,
        client: Client,
    ) -> ChatSession:
        """Attach a session only when it is unassigned or already belongs
        to the same client. Never silently reassign another client's session.
        """
        with transaction.atomic():
            session = ChatSession.objects.select_for_update().get(
                pk=session.pk
            )

            if session.client_id and session.client_id != client.pk:
                raise ValueError(
                    "Cannot attach a session belonging to another client."
                )

            if session.client_id is None:
                session.client = client
                session.save(update_fields=["client", "updated_at"])

        return session

    @staticmethod
    @transaction.atomic
    def save_episode(
        client: Client,
        session: ChatSession,
        summary: str,
        topics: list | None = None,
        outcome: str = "",
        importance: float = 0.5,
    ) -> EpisodicMemory | None:
        """Persist one meaningful conversation episode."""

        summary = (summary or "").strip()

        if not summary:
            return None

        if session.client_id != client.pk:
            raise ValueError(
                "Episode session must belong to the supplied client."
            )

        importance = max(0.0, min(1.0, float(importance)))

        clean_topics = []
        for topic in topics or []:
            if isinstance(topic, str) and topic.strip():
                clean_topics.append(topic.strip())

        return EpisodicMemory.objects.create(
            client=client,
            session=session,
            summary=summary,
            topics=clean_topics,
            outcome=(outcome or "").strip(),
            importance=importance,
        )

    @staticmethod
    @transaction.atomic
    def save_semantic_memory(
        client: Client,
        memory_type: str,
        content: str,
        source_session: ChatSession | None = None,
        confidence: float = 1.0,
        importance: float = 0.5,
    ) -> SemanticMemory | None:
        """Create a durable memory or reinforce an existing equivalent.

        Duplicate detection is intentionally conservative and exact after
        whitespace/case normalization. It does not assume that two different
        statements have the same meaning.
        """

        content = " ".join((content or "").split())
        if not content:
            return None

        allowed_types = {
            choice[0] for choice in SemanticMemory.MEMORY_TYPES
        }
        if memory_type not in allowed_types:
            raise ValueError(f"Unsupported memory type: {memory_type}")

        if source_session and source_session.client_id != client.pk:
            raise ValueError(
                "Source session must belong to the supplied client."
            )

        confidence = max(0.0, min(1.0, float(confidence)))
        importance = max(0.0, min(1.0, float(importance)))
        normalized_content = content.casefold()

        candidates = SemanticMemory.objects.select_for_update().filter(
            client=client,
            memory_type=memory_type,
            is_active=True,
        )

        existing = next(
            (
                item
                for item in candidates
                if " ".join(item.content.split()).casefold()
                == normalized_content
            ),
            None,
        )

        now = timezone.now()

        if existing:
            existing.reinforcement_count += 1
            existing.last_reinforced_at = now
            existing.confidence = max(existing.confidence, confidence)
            existing.importance = max(existing.importance, importance)

            if source_session:
                existing.source_session = source_session

            existing.save(
                update_fields=[
                    "reinforcement_count",
                    "last_reinforced_at",
                    "confidence",
                    "importance",
                    "source_session",
                    "updated_at",
                ]
            )
            return existing

        return SemanticMemory.objects.create(
            client=client,
            memory_type=memory_type,
            content=content,
            source_session=source_session,
            confidence=confidence,
            importance=importance,
            reinforcement_count=1,
            last_reinforced_at=now,
            is_active=True,
        )
