from __future__ import annotations

import json


class ServiceIntentDetector:
    """
    Determines whether the current user message should trigger
    service-related reasoning.

    This detector does NOT choose a service.

    It distinguishes between:
    - general conversation
    - direct service information requests
    - situations where service recommendation may be useful
    """

    MODEL_NAME = "claude-haiku-4-5-20251001"

    @staticmethod
    def build_prompt(
        question: str,
        conversation: str = "",
    ) -> str:

        return f"""
You are the service-intent detection layer for VYRA,
the AI assistant for Luna's Sanctum.

Your job is to determine whether the user's current message
is related to Luna's Sanctum services.

You do NOT choose a service.
You only determine whether service-related reasoning should
be considered.

Return ONLY valid JSON.

==================================================
RETURN TRUE WHEN
==================================================

Return service_intent = true when the user:

- asks what services Luna's Sanctum offers
- asks what kinds of sessions are available
- asks which service may be right for them
- asks for help choosing a service
- describes a personal situation and appears to be seeking
  clarity, guidance, or a relevant spiritual service
- discusses recurring life patterns they want to understand
- discusses relationship difficulties or relationship dynamics
- discusses career uncertainty, life transitions, timing,
  or feeling stuck
- explicitly asks whether Luna's Sanctum can help with their
  situation

Examples:

"What services do you offer?"
-> true

"Which session would be right for me?"
-> true

"I'm struggling at work and feel completely stuck."
-> true

"I keep repeating the same patterns in relationships."
-> true

==================================================
RETURN FALSE WHEN
==================================================

Return service_intent = false for:

- greetings
- casual conversation
- jokes
- thanks
- general questions about Luna's Sanctum unrelated to services
- simple factual questions about a specific service that can
  be answered directly without choosing a service
- unrelated questions

Examples:

"Hello, how are you?"
-> false

"Tell me about Luna's Sanctum."
-> false

"What is Future Fragments?"
-> false

"How much does Future Fragments cost?"
-> false

==================================================
IMPORTANT DISTINCTION
==================================================

A general question ABOUT a specific service is not necessarily
a recommendation request.

"What is Future Fragments?"
-> false

"Is Future Fragments the right service for my career situation?"
-> true

"What services does Luna's Sanctum offer?"
-> true

"Which one should I choose?"
-> true

==================================================
OUTPUT
==================================================

Return exactly this structure:

{{
    "service_intent": true,
    "confidence": 0.85
}}

or:

{{
    "service_intent": false,
    "confidence": 0.95
}}

Confidence must be a number between 0.0 and 1.0.

CURRENT USER MESSAGE
====================

{question}

RECENT CONVERSATION
===================

{conversation if conversation else "No recent conversation available."}
"""

    @staticmethod
    def clean_json_response(text: str) -> str:
        text = text.strip()

        if text.startswith("```"):
            lines = text.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        return text

    @staticmethod
    def parse_response(text: str) -> dict:

        cleaned = (
            ServiceIntentDetector
            .clean_json_response(text)
        )

        try:
            result = json.loads(cleaned)

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid service intent JSON: {exc}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError(
                "Service intent result must be an object."
            )

        service_intent = bool(
            result.get("service_intent", False)
        )

        confidence = float(
            result.get("confidence", 0.0)
        )

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        return {
            "service_intent": service_intent,
            "confidence": confidence,
        }

    @staticmethod
    def detect(
        question: str,
        claude_client,
        conversation: str = "",
    ) -> dict:

        prompt = ServiceIntentDetector.build_prompt(
            question=question,
            conversation=conversation,
        )

        response = claude_client.messages.create(
            model=ServiceIntentDetector.MODEL_NAME,
            max_tokens=150,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        if not response.content:
            raise RuntimeError(
                "Claude returned an empty service intent response."
            )

        raw_text = response.content[0].text

        result = ServiceIntentDetector.parse_response(
            raw_text
        )

        print(
            "[SERVICE INTENT] Detection:",
            result,
        )

        return result