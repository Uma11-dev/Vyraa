
from datetime import date, time
from unittest.mock import patch

from django.test import TestCase

from chatbot.models import Client as VYRAClient, ChatSession
from rag_pipeline.rag_pipeline import _route_booking


class BookingConversationFlowTests(TestCase):
    """Tests for VYRA's multi-turn booking conversation."""

    def setUp(self):
        self.client_profile = VYRAClient.objects.create(
            client_id="booking-flow-test-client",
            full_name="Test Client",
            email="test@example.com",
            whatsapp="+919876543210",
            date_of_birth=date(1999, 3, 11),
            birth_time=time(22, 25),
            birth_place="Delhi, India",
        )

        self.session = ChatSession.objects.create(
            session_id="booking-flow-test-session",
            client=self.client_profile,
        )

        self.service = "future_fragments"
        self.slot = {
            "scheduled_at": "2026-10-20T11:00:00+05:30",
            "label": "Tuesday, 20 October at 11:00 AM",
        }

        self.profile_extractor_patch = patch(
            "rag_pipeline.rag_pipeline.ProfileExtractor.extract",
            return_value={},
        )
        self.profile_extractor_patch.start()
        self.addCleanup(self.profile_extractor_patch.stop)

    
    def route(self, question, state=None):
        """Call the booking router with the selected session state."""
        return _route_booking(
            client=self.client_profile,
            session=self.session,
            question=question,
            booking_state=(
                state if state is not None else self.session.booking_state
            ),
            claude_client=object(),
        )


    def test_booking_request_without_service_asks_for_service(self):
        answer = self.route("I'd like to book a session")

        self.assertIn("awaiting_service", self.session.booking_state["state"])
        self.assertIn("Future Fragments", answer)
        self.assertIn("Unseen Alignment", answer)
        self.assertIn("Karmic Pattern Mapping", answer)

    @patch(
        "rag_pipeline.rag_pipeline.BookingConversationService.get_slots"
    )
    @patch(
        "rag_pipeline.rag_pipeline.BookingConversationService.start"
    )
    def test_service_selection_displays_available_slots(
        self, mock_start, mock_get_slots
    ):
        self.session.booking_state = {"state": "awaiting_service"}
        self.session.save(update_fields=["booking_state"])

        mock_start.return_value = {
            "state": "selecting_slot",
            "service": self.service,
            "message": "Choose a slot.",
        }
        mock_get_slots.return_value = {
            "success": True,
            "service": self.service,
            "service_duration_minutes": 60,
            "slots": [self.slot],
        }

        answer = self.route("Future Fragments")

        self.assertEqual(
            self.session.booking_state["state"], "selecting_slot"
        )
        self.assertEqual(
            self.session.booking_state["service"], self.service
        )
        self.assertEqual(
            self.session.booking_state["slots"], [self.slot]
        )
        self.assertIn(self.slot["label"], answer)
        mock_get_slots.assert_called_once()

    @patch(
        "rag_pipeline.rag_pipeline.BookingConversationService.prepare_confirmation"
    )
    def test_selecting_slot_moves_to_confirmation(self, mock_prepare):
        self.session.booking_state = {
            "state": "selecting_slot",
            "service": self.service,
            "slots": [self.slot],
        }
        self.session.save(update_fields=["booking_state"])

        mock_prepare.return_value = {
            "success": True,
            "service": self.service,
            "scheduled_at": self.slot["scheduled_at"],
        }

        answer = self.route("1")

        self.assertEqual(
            self.session.booking_state["state"],
            "awaiting_confirmation",
        )
        self.assertEqual(
            self.session.booking_state["scheduled_at"],
            self.slot["scheduled_at"],
        )
        self.assertIn("Reply yes", answer)
        self.assertIn("no to cancel", answer)
        mock_prepare.assert_called_once()

    @patch(
        "rag_pipeline.rag_pipeline.BookingConversationService.confirm"
    )
    def test_yes_creates_booking_only_after_confirmation(self, mock_confirm):
        self.session.booking_state = {
            "state": "awaiting_confirmation",
            "service": self.service,
            "scheduled_at": self.slot["scheduled_at"],
        }
        self.session.save(update_fields=["booking_state"])

        mock_confirm.return_value = {
            "success": True,
            "booking": {
                "id": 123,
                "service": "Future Fragments",
            },
        }

        answer = self.route("yes")

        mock_confirm.assert_called_once()
        self.assertEqual(self.session.booking_state, {})
        self.assertIn("pending", answer.lower())
        self.assertIn("123", answer)
        self.assertIn("not confirmed yet", answer.lower())

    @patch(
        "rag_pipeline.rag_pipeline.BookingConversationService.confirm"
    )
    def test_no_clears_state_without_creating_booking(self, mock_confirm):
        self.session.booking_state = {
            "state": "awaiting_confirmation",
            "service": self.service,
            "scheduled_at": self.slot["scheduled_at"],
        }
        self.session.save(update_fields=["booking_state"])

        answer = self.route("no")

        mock_confirm.assert_not_called()
        self.assertEqual(self.session.booking_state, {})
        self.assertIn("No booking has been created", answer)

    @patch(
        "rag_pipeline.rag_pipeline.BookingConversationService.prepare_confirmation"
    )
    def test_invalid_slot_number_does_not_prepare_booking(
        self, mock_prepare
    ):
        self.session.booking_state = {
            "state": "selecting_slot",
            "service": self.service,
            "slots": [self.slot],
        }
        self.session.save(update_fields=["booking_state"])

        answer = self.route("9")

        mock_prepare.assert_not_called()
        self.assertEqual(
            self.session.booking_state["state"], "selecting_slot"
        )
        self.assertIn("reply with a valid number", answer.lower())
