from __future__ import annotations

import re
from typing import Any

from chatbot.services.memory.memory_service import MemoryService
from chatbot.services.memory.memory_extractor import MemoryExtractor
from chatbot.services.memory.memory_retriever import HybridMemoryRetriever
from chatbot.services.client.client_service import ClientService
from chatbot.services.client.profile_extractor import ProfileExtractor
from chatbot.services.intent_detector import ServiceIntentDetector
from chatbot.services.recommendation_service import ServiceRecommendationService
from chatbot.services.booking.conversation_service import BookingConversationService
from chatbot.session_service import SessionService
from retriever.retriever import retrieve_context
from llm.claude import generate_response, load_claude


BOOKING_STATES = {
    "awaiting_service",
    "collecting_profile",
    "selecting_slot",
    "awaiting_confirmation",
}

PROFILE_LABELS = {
    "full_name": "your full name",
    "email": "your email address",
    "whatsapp": "your WhatsApp number",
    "date_of_birth": "your date of birth",
    "birth_time": "your birth time",
    "birth_place": "your birthplace",
}

SERVICE_ALIASES = {
    "future fragments": "future_fragments",
    "future fragment": "future_fragments",
    "future_fragment": "future_fragments",
    "future_fragments": "future_fragments",
    "unseen alignment": "unseen_alignment",
    "unseen_alignment": "unseen_alignment",
    "karmic pattern mapping": "karmic_pattern_mapping",
    "karmic_pattern_mapping": "karmic_pattern_mapping",
}

YES_PATTERN = re.compile(
    r"^(yes|yes please|confirm|confirm booking|go ahead|book it|"
    r"that's correct|that is correct)[.! ]*$",
    re.IGNORECASE,
)

NO_PATTERN = re.compile(
    r"^(no|no thanks|cancel|not now|don't book|do not book)[.! ]*$",
    re.IGNORECASE,
)

CANCEL_FLOW_PATTERN = re.compile(
    r"^(cancel|cancel booking|stop booking|exit booking|never mind|nevermind)[.! ]*$",
    re.IGNORECASE,
)


def build_context(documents):
    """Format retrieved knowledge documents for the response model."""
    return "\n".join(
        f"\n==========================\nDocument {index}\n"
        f"==========================\n\n{document.page_content}\n"
        for index, document in enumerate(documents, start=1)
    )


def format_history(messages):
    """Format recent persisted messages as readable conversation history."""
    role_map = {"user": "User", "assistant": "Assistant"}
    return "\n".join(
        f"{role_map.get(message.role, 'System')}: {message.content}"
        for message in messages
    )


def _service_from_text(text: str | None) -> str | None:
    """Return a supported service key only when its name appears in the text."""
    normalized = (text or "").lower().replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)

    # Prefer longer service names first.
    for alias, service in sorted(
        SERVICE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        normalized_alias = alias.replace("_", " ")
        if normalized_alias in normalized:
            return service
    return None


def _is_booking_request(question: str | None) -> bool:
    return bool(
        re.search(
            r"\b(book|booking|appointment|schedule|reserve|make an appointment)\b",
            question or "",
            re.IGNORECASE,
        )
    )


def _save_booking_state(session, state: dict[str, Any] | None) -> None:
    """Persist multi-turn booking state on this chat session."""
    session.booking_state = state or {}
    session.save(update_fields=["booking_state", "updated_at"])


def _next_missing_profile_message(client) -> str | None:
    missing = ClientService.get_missing_profile_fields(client)
    if not missing:
        return None

    field = missing[0]
    label = PROFILE_LABELS.get(field, field.replace("_", " "))
    return f"Before we check appointment availability, could you share {label}?"


def _show_available_slots(client, session, service: str) -> str:
    result = BookingConversationService.get_slots(
        client=client,
        service=service,
        days=14,
    )

    if not result.get("success"):
        missing = result.get("missing_fields", [])
        if missing:
            _save_booking_state(
                session,
                {"state": "collecting_profile", "service": service},
            )
            field = missing[0]
            label = PROFILE_LABELS.get(field, field.replace("_", " "))
            return f"Before we check availability, could you share {label}?"
        return (
            result.get("message")
            or "I couldn't check appointment availability just now. Please try again."
        )

    slots = result.get("slots", [])[:8]
    service_key = result.get("service", service)

    if not slots:
        _save_booking_state(
            session,
            {"state": "selecting_slot", "service": service_key, "slots": []},
        )
        return (
            "I couldn't find an available appointment in the next 14 days. "
            "Would you like me to check a wider date range?"
        )

    _save_booking_state(
        session,
        {
            "state": "selecting_slot",
            "service": service_key,
            "slots": slots,
        },
    )

    lines = [
        f"{index}. {slot['label']}"
        for index, slot in enumerate(slots, start=1)
    ]
    service_label = service_key.replace("_", " ").title()
    duration = result.get("service_duration_minutes")
    duration_text = f" ({duration} minutes)" if duration else ""

    return (
        f"Here are the available appointment times for {service_label}{duration_text}:\n\n"
        + "\n".join(lines)
        + "\n\nReply with the number of the time you'd like."
    )


def _select_slot(question: str | None, slots: list[dict]) -> dict | None:
    """Select a slot by its displayed number or exact display label."""
    value = (question or "").strip()
    match = re.fullmatch(r"(?:option\s*)?(\d{1,2})[.! ]*", value, re.IGNORECASE)
    if match:
        index = int(match.group(1)) - 1
        return slots[index] if 0 <= index < len(slots) else None

    normalized = re.sub(r"\s+", " ", value).strip().lower()
    exact_matches = [
        slot
        for slot in slots
        if re.sub(r"\s+", " ", slot.get("label", "")).strip().lower()
        == normalized
    ]
    return exact_matches[0] if len(exact_matches) == 1 else None


def _route_booking(
    client,
    session,
    question: str,
    booking_state: dict[str, Any] | None,
    claude_client,
) -> str | None:
    """Handle deterministic booking turns; return None for ordinary chat."""
    state_data = booking_state if isinstance(booking_state, dict) else {}
    current_state = state_data.get("state")
    active = current_state in BOOKING_STATES
    booking_request = _is_booking_request(question)

    if not active and not booking_request:
        return None

    if CANCEL_FLOW_PATTERN.fullmatch((question or "").strip()):
        _save_booking_state(session, {})
        return "I've stopped the booking process. No new booking has been created."

    # Profile extraction is best-effort and only possible when Claude is available.
    if claude_client is not None:
        try:
            ProfileExtractor.extract(
                client=client,
                user_message=question,
                claude_client=claude_client,
            )
            client.refresh_from_db()
        except Exception as exc:
            print(f"[PROFILE] Booking intake extraction error: {exc}")

    if current_state == "awaiting_service":
        service = _service_from_text(question)
        if not service:
            return (
                "Which Luna's Sanctum service would you like to book: "
                "Future Fragments, Unseen Alignment, or Karmic Pattern Mapping?"
            )
        # The user has supplied the requested service. Start the flow below.
        active = False
        booking_request = True

    if not active and booking_request:
        service = _service_from_text(question)
        if not service:
            _save_booking_state(session, {"state": "awaiting_service"})
            return (
                "I'd be happy to help you book a session. Which service would you like: "
                "Future Fragments, Unseen Alignment, or Karmic Pattern Mapping?"
            )

        result = BookingConversationService.start(client=client, service=service)
        if result.get("state") == "collecting_profile":
            _save_booking_state(
                session,
                {"state": "collecting_profile", "service": result["service"]},
            )
            return (
                _next_missing_profile_message(client)
                or result.get("message", "Please complete your client profile.")
            )

        if not result.get("success", True):
            return result.get("message", "I couldn't start the booking process. Please try again.")
        return _show_available_slots(client, session, result["service"])

    if current_state == "collecting_profile":
        service = state_data.get("service")
        missing_message = _next_missing_profile_message(client)
        if missing_message:
            return missing_message
        if not service:
            _save_booking_state(session, {"state": "awaiting_service"})
            return "Which Luna's Sanctum service would you like to book?"
        return _show_available_slots(client, session, service)

    if current_state == "selecting_slot":
        slots = state_data.get("slots", [])
        service = state_data.get("service")
        if not service:
            _save_booking_state(session, {"state": "awaiting_service"})
            return "Which Luna's Sanctum service would you like to book?"
        if not slots:
            return _show_available_slots(client, session, service)

        selected = _select_slot(question, slots)
        if selected is None:
            return (
                "Please reply with a valid number from the available appointment list "
                "so I can select the correct time."
            )

        result = BookingConversationService.prepare_confirmation(
            client=client,
            service=service,
            scheduled_at=selected["scheduled_at"],
        )
        if not result.get("success"):
            # Slots can become unavailable after being displayed; refresh the list.
            return _show_available_slots(client, session, service)

        _save_booking_state(
            session,
            {
                "state": "awaiting_confirmation",
                "service": result["service"],
                "scheduled_at": result["scheduled_at"],
                "slot_label": selected["label"],
            },
        )
        return (
            f"You selected {selected['label']} for {service.replace('_', ' ').title()}. "
            "Would you like me to create this booking? Reply yes to proceed or no to cancel."
        )

    if current_state == "awaiting_confirmation":
        if NO_PATTERN.fullmatch((question or "").strip()):
            _save_booking_state(session, {})
            return "No booking has been created. Let me know if you'd like to choose another time."

        if not YES_PATTERN.fullmatch((question or "").strip()):
            return (
                "Would you like me to create the booking for the selected time? "
                "Reply yes to proceed or no to cancel."
            )

        service = state_data.get("service")
        scheduled_at = state_data.get("scheduled_at")
        if not service or not scheduled_at:
            _save_booking_state(session, {"state": "awaiting_service"})
            return "I lost the selected booking details. Which service would you like to book?"

        result = BookingConversationService.confirm(
            client=client,
            service=service,
            scheduled_at=scheduled_at,
            session=session,
        )
        if not result.get("success"):
            reason = result.get("reason")
            if reason == "profile_incomplete":
                _save_booking_state(
                    session,
                    {"state": "collecting_profile", "service": service},
                )
                return (
                    _next_missing_profile_message(client)
                    or result.get("message", "Please complete your client profile.")
                )
            if reason == "slot_unavailable":
                _save_booking_state(
                    session,
                    {"state": "selecting_slot", "service": service, "slots": []},
                )
                return _show_available_slots(client, session, service)
            return result.get(
                "message",
                "I couldn't create the booking. No booking was confirmed.",
            )

        _save_booking_state(session, {})
        booking = result.get("booking") or {}
        if hasattr(booking, "id"):
            booking_id = booking.id
            service_label = booking.get_service_display() if hasattr(booking, "get_service_display") else service.replace("_", " ").title()
            status = getattr(booking, "status", "pending")
        else:
            booking_id = booking.get("id", "Created") if isinstance(booking, dict) else "Created"
            service_label = booking.get("service", service.replace("_", " ").title()) if isinstance(booking, dict) else service.replace("_", " ").title()
            status = booking.get("status", "pending") if isinstance(booking, dict) else "pending"

        return (
            "Your booking has been created and is currently pending confirmation.\n\n"
            f"Service: {service_label}\n"
            f"Booking ID: {booking_id}\n"
            f"Status: {str(status).title()}\n\n"
            "It is not confirmed yet."
        )

    return None


def ask_vyra(client_id, session_id, question, collection_name):
    """Run VYRA's knowledge retrieval, memory, recommendation, and booking pipeline."""
    question = (question or "").strip()
    if not question:
        return "Please enter a message so I can help."

    print("=" * 70)
    print("[VYRA] PIPELINE START")
    print("=" * 70)

    client, created = ClientService.get_or_create_client(client_id=client_id)
    print(f"[VYRA] {'New' if created else 'Existing'} client: {client_id}")

    session = SessionService.get_or_create_session(session_id=session_id, client=client)
    MemoryService.attach_session_to_client(session=session, client=client)

    memory_context = ""
    try:
        memory_results = HybridMemoryRetriever.retrieve(
            client=client,
            query=question,
            semantic_limit=5,
            episodic_limit=5,
        )
        memory_context = HybridMemoryRetriever.format_for_llm(memory_results)
    except Exception as exc:
        print(f"[MEMORY] Retrieval error: {exc}")

    try:
        history_messages = SessionService.get_recent_messages(session=session, limit=20)
        history = format_history(history_messages)
    except Exception as exc:
        print(f"[SESSION] History retrieval error: {exc}")
        history = ""

    try:
        documents = retrieve_context(question=question, collection_name=collection_name)
        context = build_context(documents)
    except Exception as exc:
        print(f"[RAG] Knowledge retrieval error: {exc}")
        context = ""

    service_recommendation = None
    claude_client = None
    try:
        claude_client = load_claude()
        intent_result = ServiceIntentDetector.detect(
            question=question,
            claude_client=claude_client,
            conversation=history,
        )
        if intent_result.get("service_intent"):
            service_recommendation = ServiceRecommendationService.recommend(
                question=question,
                claude_client=claude_client,
                conversation=history,
                knowledge=context,
                memory=memory_context,
            )
        print("[VYRA] Service intent:", intent_result.get("service_intent"))
    except Exception as exc:
        print(f"[SERVICE] Recommendation processing error: {exc}")

    SessionService.save_message(session=session, role="user", content=question)

    # Reload state immediately before routing so each turn uses persisted state.
    try:
        session.refresh_from_db(fields=["booking_state"])
    except Exception:
        pass
    booking_state_before_turn = getattr(session, "booking_state", {}) or {}

    answer = None
    try:
        answer = _route_booking(
            client=client,
            session=session,
            question=question,
            booking_state=booking_state_before_turn,
            claude_client=claude_client,
        )
    except Exception as exc:
        print(f"[BOOKING] Conversation routing error: {exc}")
        answer = (
            "I'm sorry, I couldn't complete that booking step. "
            "No booking confirmation should be assumed. Please try again."
        )

    if answer is None:
        answer = generate_response(
            question=question,
            context=context,
            history=history,
            memory=memory_context,
            service_recommendation=service_recommendation,
        )

    if not answer:
        raise RuntimeError("VYRA generated an empty response.")

    SessionService.save_message(session=session, role="assistant", content=answer)

    # Enrichment is best-effort and should not invalidate the response.
    try:
        if claude_client is None:
            claude_client = load_claude()

        try:
            memory_result = MemoryExtractor.extract(
                client=client,
                session=session,
                user_message=question,
                assistant_response=answer,
                claude_client=claude_client,
            )
            print(
                "[VYRA] Memory processing complete: "
                f"episode={'yes' if memory_result.get('episode') else 'no'}, "
                f"semantic={len(memory_result.get('semantic_memories', []))}"
            )
        except Exception as exc:
            print(f"[MEMORY] Processing error: {exc}")

        # Booking flow extracts profile details before routing. Ordinary chat keeps
        # the original post-response profile extraction behavior.
        if not booking_state_before_turn and not _is_booking_request(question):
            try:
                profile_result = ProfileExtractor.extract(
                    client=client,
                    user_message=question,
                    claude_client=claude_client,
                )
                print(
                    "[VYRA] Profile updated:",
                    list(profile_result.get("profile", {}).keys()),
                )
            except Exception as exc:
                print(f"[PROFILE] Processing error: {exc}")
    except Exception as exc:
        print(f"[VYRA] Post-response processing error: {exc}")

    print("=" * 70)
    print("[VYRA] PIPELINE COMPLETE")
    print("=" * 70)
    return answer
