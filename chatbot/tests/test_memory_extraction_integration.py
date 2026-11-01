
import json
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import TestCase

from chatbot.models import (
    Client,
    ChatSession,
    SemanticMemory,
    EpisodicMemory,
)
from chatbot.services.memory.memory_extractor import MemoryExtractor
from chatbot.services.memory.memory_retriever import HybridMemoryRetriever


class MemoryExtractionIntegrationTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            client_id="extract-integration-client",
            full_name="Memory Integration Test",
        )

        self.session = ChatSession.objects.create(
            session_id="extract-integration-session",
            client=self.client_record,
        )

    def test_extraction_saves_memories_and_retriever_finds_them(self):
        extraction_result = {
            "episode": {
                "summary": "Client discussed career development.",
                "topics": ["career", "development"],
                "outcome": "Wants practical next steps.",
                "importance": 0.8,
            },
            "semantic_memories": [
                {
                    "type": "preference",
                    "content": "Prefers practical step-by-step guidance",
                    "confidence": 0.95,
                    "importance": 0.9,
                }
            ],
        }

        claude_client = Mock()
        claude_client.messages.create.return_value = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text=json.dumps(extraction_result),
                )
            ]
        )

        result = MemoryExtractor.extract(
            client=self.client_record,
            session=self.session,
            user_message="I prefer practical step-by-step guidance.",
            assistant_response="I'll keep my guidance practical.",
            claude_client=claude_client,
        )

        self.assertIsNotNone(result["episode"])
        self.assertEqual(len(result["semantic_memories"]), 1)

        self.assertTrue(
            EpisodicMemory.objects.filter(
                client=self.client_record,
                session=self.session,
                summary="Client discussed career development.",
            ).exists()
        )

        self.assertTrue(
            SemanticMemory.objects.filter(
                client=self.client_record,
                content="Prefers practical step-by-step guidance",
                is_active=True,
            ).exists()
        )

        retrieved = HybridMemoryRetriever.retrieve(
            client=self.client_record,
            query="practical step-by-step guidance",
            semantic_limit=5,
            episodic_limit=5,
        )

        formatted = HybridMemoryRetriever.format_for_llm(retrieved)

        self.assertIn("Prefers practical step-by-step guidance", formatted)
        self.assertTrue(retrieved["episodic"])

    def test_low_confidence_candidate_is_not_saved(self):
        response = {
            "episode": None,
            "semantic_memories": [
                {
                    "type": "preference",
                    "content": "Possibly likes short answers",
                    "confidence": 0.3,
                    "importance": 0.5,
                }
            ],
        }

        claude_client = Mock()
        claude_client.messages.create.return_value = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text=json.dumps(response),
                )
            ]
        )

        result = MemoryExtractor.extract(
            client=self.client_record,
            session=self.session,
            user_message="Maybe short answers?",
            assistant_response="I can adapt my style.",
            claude_client=claude_client,
        )

        self.assertEqual(result["semantic_memories"], [])
        self.assertEqual(
            SemanticMemory.objects.filter(
                client=self.client_record,
                content="Possibly likes short answers",
            ).count(),
            0,
        )
