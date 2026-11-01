
from django.test import TestCase

from chatbot.models import (
    Client,
    ChatSession,
    SemanticMemory,
    EpisodicMemory,
)
from chatbot.services.memory.memory_service import MemoryService
from chatbot.services.memory.memory_retriever import HybridMemoryRetriever


class HybridMemoryTests(TestCase):
    def setUp(self):
        self.client_a = Client.objects.create(
            client_id="memory-test-client-a",
            full_name="Test Client A",
        )
        self.session_a = ChatSession.objects.create(
            session_id="memory-test-session-a",
            client=self.client_a,
        )

    def test_save_semantic_memory(self):
        memory = MemoryService.save_semantic_memory(
            self.client_a,
            memory_type="preference",
            content="Prefers detailed explanations",
            source_session=self.session_a,
            confidence=0.95,
            importance=0.8,
        )

        self.assertIsNotNone(memory)
        self.assertEqual(
            SemanticMemory.objects.filter(
                client=self.client_a,
                content="Prefers detailed explanations",
                is_active=True,
            ).count(),
            1,
        )

    def test_save_episodic_memory(self):
        episode = MemoryService.save_episode(
            self.client_a,
            self.session_a,
            "Client discussed a career transition",
            ["career", "transition"],
            "Exploring possible next steps",
            0.8,
        )

        self.assertIsNotNone(episode)
        self.assertEqual(
            EpisodicMemory.objects.filter(
                client=self.client_a,
                session=self.session_a,
            ).count(),
            1,
        )

    def test_retriever_returns_both_memory_types(self):
        SemanticMemory.objects.create(
            client=self.client_a,
            memory_type="goal",
            content="Wants to transition into generative AI",
            confidence=0.95,
            importance=0.9,
        )

        EpisodicMemory.objects.create(
            client=self.client_a,
            session=self.session_a,
            summary="Discussed a generative AI career plan",
            topics=["career", "generative AI"],
            outcome="Needs a learning roadmap",
            importance=0.8,
        )

        results = HybridMemoryRetriever.retrieve(
            client=self.client_a,
            query="generative AI career",
            semantic_limit=5,
            episodic_limit=5,
        )

        self.assertIn("semantic", results)
        self.assertIn("episodic", results)
        self.assertTrue(results["semantic"])
        self.assertTrue(results["episodic"])

    def test_retrieval_does_not_leak_other_clients_memories(self):
        other_client = Client.objects.create(
            client_id="memory-test-client-b",
            full_name="Test Client B",
        )

        SemanticMemory.objects.create(
            client=other_client,
            memory_type="preference",
            content="Secret test phrase for client B",
            confidence=1.0,
            importance=1.0,
        )

        results = HybridMemoryRetriever.retrieve(
            client=self.client_a,
            query="Secret test phrase for client B",
            semantic_limit=5,
            episodic_limit=5,
        )

        formatted = HybridMemoryRetriever.format_for_llm(results)

        self.assertNotIn("Secret test phrase for client B", formatted)
