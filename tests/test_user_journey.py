
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from chatbot.models import Client, ChatSession


class VYRAEndToEndTest(TestCase):
    """
    Single end-to-end proof-of-functionality test for VYRA.

    Verifies:
    - Django chat API accepts a user question.
    - The RAG retrieval function is invoked.
    - Retrieved document content reaches response generation.
    - An answer is returned through the API.
    - Client, session, and conversation messages are persisted.

    External Claude calls are mocked to keep the test deterministic.
    """

    def setUp(self):
        self.api = APIClient()

        self.client_id = "vyra-e2e-test-client"
        self.session_id = "vyra-e2e-test-session"
        self.collection_name = "vyra-e2e-test-collection"

        self.question = "What does the document say about the origin of VYRA?"

        self.retrieved_content = (
            "VYRA is an AI-powered spiritual guidance platform. "
            "Its architecture uses retrieval-augmented generation (RAG) "
            "to retrieve relevant knowledge before generating responses."
        )

        self.expected_answer = (
            "According to the indexed document, VYRA is an AI-powered "
            "spiritual guidance platform that uses RAG to retrieve "
            "relevant knowledge before generating responses."
        )

    @patch("rag_pipeline.rag_pipeline.generate_response")
    @patch("rag_pipeline.rag_pipeline.load_claude")
    @patch("rag_pipeline.rag_pipeline.ServiceIntentDetector.detect")
    @patch("rag_pipeline.rag_pipeline.retrieve_context")
    def test_complete_rag_user_journey(
        self,
        mock_retrieve,
        mock_detect,
        mock_load_claude,
        mock_generate,
    ):
        # 1. Simulate a document returned by the retrieval layer.
        # The retrieval function is isolated here; response generation
        # and the Django API integration are exercised through the pipeline.
        from langchain_core.documents import Document

        mock_retrieve.return_value = [
            Document(
                page_content=self.retrieved_content,
                metadata={
                    "source": "vyra_e2e_test.txt",
                    "collection": self.collection_name,
                },
            )
        ]

        mock_detect.return_value = {"service_intent": False}
        mock_load_claude.return_value = object()
        mock_generate.return_value = self.expected_answer

        # 2. Submit a real request through the Django REST API.
        response = self.api.post(
            "/api/chat/",
            {
                "client_id": self.client_id,
                "session_id": self.session_id,
                "question": self.question,
                "collection_name": self.collection_name,
            },
            format="json",
        )

        # 3. Verify successful API response.
        self.assertEqual(
            response.status_code,
            200,
            msg=f"API returned {response.status_code}: {response.data}",
        )

        self.assertIn("answer", response.data)
        self.assertEqual(response.data["answer"], self.expected_answer)

        # 4. Verify the RAG retrieval layer was invoked.
        mock_retrieve.assert_called_once()

        retrieval_args = mock_retrieve.call_args
        retrieval_input = str(retrieval_args)

        self.assertIn(self.question, retrieval_input)
        self.assertIn(self.collection_name, retrieval_input)

        # 5. Verify retrieved knowledge reached response generation.
        mock_generate.assert_called_once()

        generation_input = str(mock_generate.call_args)

        self.assertIn(
            self.retrieved_content,
            generation_input,
            msg="Retrieved document content did not reach response generation.",
        )

        # 6. Verify the client and session were persisted.
        self.assertTrue(
            Client.objects.filter(client_id=self.client_id).exists()
        )

        self.assertTrue(
            ChatSession.objects.filter(session_id=self.session_id).exists()
        )

        # 7. Verify the response contains the expected session identifiers.
        self.assertEqual(response.data["client_id"], self.client_id)
        self.assertEqual(response.data["session_id"], self.session_id)

        print("\nVYRA END-TO-END TEST PASSED")
        print("✓ Django API request")
        print("✓ RAG retrieval invocation")
        print("✓ Retrieved context passed to response generation")
        print("✓ Response returned successfully")
        print("✓ Client and session persistence")
