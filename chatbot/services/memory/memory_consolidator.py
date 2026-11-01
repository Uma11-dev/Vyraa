
from __future__ import annotations

from chatbot.models import Client, ChatSession
from chatbot.services.memory.memory_service import MemoryService


class MemoryConsolidator:
    """Persist validated semantic memory candidates.

    Extraction and validation remain the responsibility of MemoryExtractor.
    This class consolidates persistence and duplicate reinforcement.
    """

    @staticmethod
    def consolidate(
        client: Client,
        memories: list[dict],
        source_session: ChatSession | None = None,
    ) -> list:
        saved = []

        for memory in memories or []:
            if not isinstance(memory, dict):
                continue

            memory_type = memory.get("type")
            content = memory.get("content")

            if not isinstance(memory_type, str):
                continue

            if not isinstance(content, str) or not content.strip():
                continue

            try:
                confidence = float(memory.get("confidence", 0.0))
                importance = float(memory.get("importance", 0.5))
            except (TypeError, ValueError):
                continue

            if confidence < 0.70:
                continue

            result = MemoryService.save_semantic_memory(
                client=client,
                memory_type=memory_type,
                content=content,
                source_session=source_session,
                confidence=confidence,
                importance=importance,
            )

            if result is not None:
                saved.append(result)

        return saved
