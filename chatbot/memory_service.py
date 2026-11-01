from __future__ import annotations

from typing import Optional

from django.utils import timezone

from chatbot.models import (
    Client,
    SemanticMemory,
    EpisodicMemory,
    ChatSession,
)


class MemoryService:
    """
    Central service for VYRA's long-term memory system.

    Memory is divided into:

    Semantic memory:
        Durable knowledge about the client.

    Episodic memory:
        Meaningful events or conversations involving the client.
    """

    # ========================================================
    # CLIENT
    # ========================================================

    @staticmethod
    def get_or_create_client(
        client_id: str,
    ) -> Client:

        client, created = Client.objects.get_or_create(
            client_id=client_id,
        )

        if created:
            print(
                f"[MEMORY] Created client: {client_id}"
            )
        else:
            print(
                f"[MEMORY] Loaded client: {client_id}"
            )

        return client

    # ========================================================
    # SESSION
    # ========================================================

    @staticmethod
    def attach_session_to_client(
        session: ChatSession,
        client: Client,
    ) -> ChatSession:

        if session.client_id != client.id:

            session.client = client

            session.save(
                update_fields=["client"]
            )

        return session

    # ========================================================
    # SEMANTIC MEMORY
    # ========================================================

    @staticmethod
    def save_semantic_memory(
        client: Client,
        memory_type: str,
        content: str,
        source_session: Optional[ChatSession] = None,
        confidence: float = 1.0,
        importance: float = 0.5,
    ) -> SemanticMemory:

        content = content.strip()

        if not content:
            raise ValueError(
                "Semantic memory content cannot be empty."
            )

        confidence = max(
            0.0,
            min(1.0, float(confidence)),
        )

        importance = max(
            0.0,
            min(1.0, float(importance)),
        )

        existing = SemanticMemory.objects.filter(
            client=client,
            memory_type=memory_type,
            content__iexact=content,
            is_active=True,
        ).first()

        if existing:

            existing.reinforcement_count += 1
            existing.last_reinforced_at = timezone.now()

            existing.confidence = max(
                existing.confidence,
                confidence,
            )

            existing.importance = max(
                existing.importance,
                importance,
            )

            existing.save(
                update_fields=[
                    "reinforcement_count",
                    "last_reinforced_at",
                    "confidence",
                    "importance",
                    "updated_at",
                ]
            )

            print(
                "[MEMORY] Reinforced semantic memory:"
                f" [{memory_type}] {content}"
            )

            return existing

        memory = SemanticMemory.objects.create(
            client=client,
            memory_type=memory_type,
            content=content,
            source_session=source_session,
            confidence=confidence,
            importance=importance,
            reinforcement_count=1,
            last_reinforced_at=timezone.now(),
        )

        print(
            "[MEMORY] Created semantic memory:"
            f" [{memory_type}] {content}"
        )

        return memory

    # ========================================================
    # GET SEMANTIC MEMORIES
    # ========================================================

    @staticmethod
    def get_semantic_memories(
        client: Client,
        limit: int = 20,
    ):

        return list(
            SemanticMemory.objects.filter(
                client=client,
                is_active=True,
            )
            .order_by(
                "-importance",
                "-updated_at",
            )[:limit]
        )

    # ========================================================
    # FORMAT SEMANTIC MEMORY
    # ========================================================

    @staticmethod
    def format_semantic_memories(
        memories,
    ) -> str:

        if not memories:
            return ""

        output = (
            "Known information about this client:\n"
        )

        for memory in memories:

            output += (
                f"- [{memory.memory_type}] "
                f"{memory.content}\n"
            )

        return output

    # ========================================================
    # EPISODIC MEMORY
    # ========================================================

    @staticmethod
    def save_episode(
        client: Client,
        session: ChatSession,
        summary: str,
        topics: Optional[list] = None,
        outcome: str = "",
        importance: float = 0.5,
    ) -> EpisodicMemory:

        summary = summary.strip()

        if not summary:
            raise ValueError(
                "Episode summary cannot be empty."
            )

        importance = max(
            0.0,
            min(1.0, float(importance)),
        )

        episode = EpisodicMemory.objects.create(
            client=client,
            session=session,
            summary=summary,
            topics=topics or [],
            outcome=outcome.strip(),
            importance=importance,
        )

        print(
            "[MEMORY] Saved episode:"
            f" {summary}"
        )

        return episode

    # ========================================================
    # GET EPISODIC MEMORIES
    # ========================================================

    @staticmethod
    def get_episodes(
        client: Client,
        limit: int = 10,
    ):

        return list(
            EpisodicMemory.objects.filter(
                client=client,
            )
            .order_by(
                "-importance",
                "-occurred_at",
            )[:limit]
        )

    # ========================================================
    # FORMAT EPISODIC MEMORY
    # ========================================================

    @staticmethod
    def format_episodes(
        episodes,
    ) -> str:

        if not episodes:
            return ""

        output = (
            "Relevant past interactions with this client:\n"
        )

        for episode in episodes:

            output += (
                f"- {episode.summary}\n"
            )

            if episode.outcome:
                output += (
                    f"  Outcome: "
                    f"{episode.outcome}\n"
                )

        return output

    # ========================================================
    # DEACTIVATE SEMANTIC MEMORY
    # ========================================================

    @staticmethod
    def deactivate_semantic_memory(
        memory: SemanticMemory,
    ):

        memory.is_active = False

        memory.save(
            update_fields=["is_active"]
        )

        print(
            "[MEMORY] Deactivated semantic memory:"
            f" {memory.id}"
        )