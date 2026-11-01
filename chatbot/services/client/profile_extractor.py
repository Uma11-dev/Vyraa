from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from chatbot.models import Client
from chatbot.services.client.client_service import ClientService


MODEL_NAME = "claude-haiku-4-5-20251001"
MAX_TOKENS = 700


class ProfileExtractor:
    """
    Extracts structured client profile information from the
    CURRENT user message only.

    The LLM identifies possible fields.
    Python validates and updates the Client record.
    """

    ALLOWED_FIELDS = {
        "full_name",
        "email",
        "whatsapp",
        "date_of_birth",
        "birth_time",
        "birth_place",
    }

    @staticmethod
    def build_prompt(user_message: str) -> str:
        return f"""
You are VYRA's client profile extraction system.

Extract client profile information explicitly stated by the
CLIENT in the CURRENT message.

Do NOT use previous conversation history.
Do NOT infer missing information.
Do NOT treat information from an assistant message as client data.

Possible fields:

- full_name
- email
- whatsapp
- date_of_birth
- birth_time
- birth_place

Only extract a field when the client explicitly provides it.

Examples:

"I am Uma"
→ full_name = "Uma"

"My name is Uma Chauhan and my email is uma@example.com"
→ full_name = "Uma Chauhan"
→ email = "uma@example.com"

"I was born on 11 March 1999"
→ date_of_birth = "1999-03-11"

"My birth time is 10:25 PM"
→ birth_time = "22:25"

"I was born in Delhi"
→ birth_place = "Delhi"

If nothing relevant is provided, return:

{{
  "profile": {{}}
}}

Return ONLY valid JSON.

CURRENT CLIENT MESSAGE
======================

{user_message}

Return:

{{
  "profile": {{
    "full_name": "...",
    "email": "...",
    "whatsapp": "...",
    "date_of_birth": "YYYY-MM-DD",
    "birth_time": "HH:MM",
    "birth_place": "..."
  }}
}}

Only include fields explicitly present in the message.
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
        cleaned = ProfileExtractor.clean_json_response(text)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Profile extractor returned invalid JSON: {exc}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError(
                "Profile extraction result must be an object."
            )

        profile = result.get("profile", {})

        if not isinstance(profile, dict):
            raise ValueError(
                "Profile must be an object."
            )

        cleaned_profile = {}

        for field, value in profile.items():

            if field not in ProfileExtractor.ALLOWED_FIELDS:
                continue

            if value is None:
                continue

            if isinstance(value, str):
                value = value.strip()

            if value == "":
                continue

            cleaned_profile[field] = value

        return {
            "profile": cleaned_profile
        }

    @staticmethod
    def normalize_date(value: str) -> Optional[str]:
        """
        Validate ISO date returned by Claude.
        """

        try:
            parsed = datetime.strptime(
                value,
                "%Y-%m-%d",
            )

            return parsed.date().isoformat()

        except (ValueError, TypeError):
            return None

    @staticmethod
    def normalize_time(value: str) -> Optional[str]:
        """
        Normalize HH:MM or HH:MM:SS into HH:MM.
        """

        if not isinstance(value, str):
            return None

        value = value.strip()

        for fmt in (
            "%H:%M",
            "%H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(
                    value,
                    fmt,
                )

                return parsed.strftime("%H:%M")

            except ValueError:
                continue

        return None

    @staticmethod
    def validate_profile(profile: dict) -> dict:
        """
        Validate and normalize extracted profile data
        before it reaches the database.
        """

        validated = {}

        # -----------------------------
        # Name
        # -----------------------------

        if profile.get("full_name"):
            name = str(
                profile["full_name"]
            ).strip()

            if len(name) <= 255:
                validated["full_name"] = name

        # -----------------------------
        # Email
        # -----------------------------

        if profile.get("email"):
            email = str(
                profile["email"]
            ).strip()

            email_pattern = (
                r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
            )

            if re.match(
                email_pattern,
                email,
            ):
                validated["email"] = email

        # -----------------------------
        # WhatsApp
        # -----------------------------

        if profile.get("whatsapp"):
            whatsapp = str(
                profile["whatsapp"]
            ).strip()

            # Keep +, digits, spaces, hyphens and parentheses.
            whatsapp = re.sub(
                r"[^\d+\-\s()]",
                "",
                whatsapp,
            ).strip()

            if whatsapp:
                validated["whatsapp"] = whatsapp

        # -----------------------------
        # Date of birth
        # -----------------------------

        if profile.get("date_of_birth"):

            date_value = (
                ProfileExtractor.normalize_date(
                    profile["date_of_birth"]
                )
            )

            if date_value:
                validated[
                    "date_of_birth"
                ] = date_value

        # -----------------------------
        # Birth time
        # -----------------------------

        if profile.get("birth_time"):

            time_value = (
                ProfileExtractor.normalize_time(
                    profile["birth_time"]
                )
            )

            if time_value:
                validated[
                    "birth_time"
                ] = time_value

        # -----------------------------
        # Birth place
        # -----------------------------

        if profile.get("birth_place"):

            birth_place = str(
                profile["birth_place"]
            ).strip()

            if len(birth_place) <= 255:
                validated[
                    "birth_place"
                ] = birth_place

        return validated

    @staticmethod
    def update_client(
        client: Client,
        profile: dict,
    ) -> Client:

        if not profile:
            return client

        validated = (
            ProfileExtractor.validate_profile(
                profile
            )
        )

        if not validated:
            return client

        updated_client = (
            ClientService.update_client(
                client,
                **validated,
            )
        )

        print(
            "[PROFILE] Updated fields:",
            ", ".join(validated.keys()),
        )

        return updated_client

    @staticmethod
    def extract(
        client: Client,
        user_message: str,
        claude_client,
    ) -> dict:

        prompt = (
            ProfileExtractor.build_prompt(
                user_message
            )
        )

        response = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
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
                "Claude returned an empty profile response."
            )

        raw_text = response.content[0].text

        parsed = (
            ProfileExtractor.parse_response(
                raw_text
            )
        )

        profile = parsed.get(
            "profile",
            {},
        )

        validated_profile = (
            ProfileExtractor.validate_profile(
                profile
            )
        )

        if validated_profile:
            ProfileExtractor.update_client(
                client=client,
                profile=validated_profile,
            )

        return {
            "profile": validated_profile
        }