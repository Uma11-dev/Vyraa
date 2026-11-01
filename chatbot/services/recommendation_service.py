from __future__ import annotations

import json
from typing import Optional


class ServiceRecommendationService:
    """
    Determines whether VYRA has enough information to recommend
    a Luna's Sanctum service.

    Claude handles interpretation.
    Python validates the structured result.

    The actual service descriptions, prices, and details remain
    in the Luna's Sanctum knowledge base.
    """

    MODEL_NAME = "claude-haiku-4-5-20251001"

    ALLOWED_SERVICES = {
        "Future Fragments",
        "Unseen Alignment",
        "Karmic Pattern Mapping",
        None,
    }

    @staticmethod
    def build_prompt(
        question: str,
        conversation: str = "",
        knowledge: str = "",
        memory: str = "",
    ) -> str:

        return f"""
You are the service recommendation reasoning layer for VYRA,
the AI assistant for Luna's Sanctum.

Your job is NOT to perform a spiritual reading.

Your job is to determine whether the client's current need is
clear enough to recommend one of Luna's Sanctum's services.

Use the Luna's Sanctum knowledge provided below as the source of
truth for what each service is designed to explore.

Do not invent services.

Do not invent service descriptions.

Do not recommend a service simply because a keyword appears.

Understand the client's underlying question or need.

If the client's need is unclear, ask for clarification rather
than forcing a recommendation.

A client may be dealing with several areas of life at once.
Identify what they most want clarity about.

If there is enough information to recommend a service, choose
ONE best-fit service.

If there is not enough information, return:
- no service
- needs_clarification = true
- one concise question that would help determine the right
  direction.

Return ONLY valid JSON.

Expected format:

{{
    "recommended_service": null,
    "confidence": 0.0,
    "reason": "",
    "needs_clarification": true,
    "clarifying_question": ""
}}

OR:

{{
    "recommended_service": "Future Fragments",
    "confidence": 0.85,
    "reason": "The client is primarily looking for clarity about their current life phase and what may be unfolding.",
    "needs_clarification": false,
    "clarifying_question": ""
}}

CURRENT CLIENT MESSAGE
======================

{question}


RECENT CONVERSATION
===================

{conversation if conversation else "No recent conversation available."}


RELEVANT CLIENT MEMORY
======================

{memory if memory else "No relevant memory available."}


LUNA'S SANCTUM KNOWLEDGE
========================

{knowledge if knowledge else "No relevant service knowledge available."}
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
            ServiceRecommendationService
            .clean_json_response(text)
        )

        try:
            result = json.loads(cleaned)

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid recommendation JSON: {exc}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError(
                "Recommendation result must be an object."
            )

        service = result.get(
            "recommended_service"
        )

        if service not in (
            ServiceRecommendationService.ALLOWED_SERVICES
        ):
            raise ValueError(
                f"Invalid service recommendation: {service}"
            )

        confidence = float(
            result.get("confidence", 0.0)
        )

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        needs_clarification = bool(
            result.get(
                "needs_clarification",
                False,
            )
        )

        reason = str(
            result.get("reason", "")
        ).strip()

        clarifying_question = str(
            result.get(
                "clarifying_question",
                "",
            )
        ).strip()

        # If Claude says clarification is needed,
        # there should not be a forced recommendation.
        if needs_clarification:
            service = None

        # If there is no service, clarification is required.
        if service is None:
            needs_clarification = True

        return {
            "recommended_service": service,
            "confidence": confidence,
            "reason": reason,
            "needs_clarification": needs_clarification,
            "clarifying_question": clarifying_question,
        }

    @staticmethod
    def recommend(
        question: str,
        claude_client,
        conversation: str = "",
        knowledge: str = "",
        memory: str = "",
    ) -> dict:

        prompt = (
            ServiceRecommendationService
            .build_prompt(
                question=question,
                conversation=conversation,
                knowledge=knowledge,
                memory=memory,
            )
        )

        response = claude_client.messages.create(
            model=ServiceRecommendationService.MODEL_NAME,
            max_tokens=500,
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
                "Claude returned an empty service recommendation."
            )

        raw_text = response.content[0].text

        result = (
            ServiceRecommendationService
            .parse_response(raw_text)
        )

        print(
            "[SERVICE] Recommendation:",
            result,
        )

        return result