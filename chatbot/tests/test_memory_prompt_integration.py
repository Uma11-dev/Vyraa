
from django.test import SimpleTestCase

from llm.prompt import build_prompt


class MemoryPromptIntegrationTests(SimpleTestCase):
    def test_semantic_and_episodic_memory_reach_prompt(self):
        memory = """
        SEMANTIC MEMORIES
        - Prefers detailed explanations.

        EPISODIC MEMORIES
        - Previously discussed changing careers.
        """

        prompt = build_prompt(
            question="What should I focus on next?",
            context="Relevant knowledge context",
            history="User: I want to plan my next steps.",
            memory=memory,
        )

        self.assertIn("Prefers detailed explanations", prompt)
        self.assertIn("Previously discussed changing careers", prompt)
        self.assertIn("What should I focus on next?", prompt)

    def test_empty_memory_does_not_break_prompt(self):
        prompt = build_prompt(
            question="What services do you offer?",
            context="Luna's Sanctum service information",
            history="",
            memory="",
        )

        self.assertIn("What services do you offer?", prompt)
        self.assertIn("None available.", prompt)
