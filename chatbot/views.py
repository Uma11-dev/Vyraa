import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import ChatSerializer
from rag_pipeline.rag_pipeline import ask_vyra

logger = logging.getLogger(__name__)


class ChatAPIView(APIView):
    def post(self, request):
        serializer = ChatSerializer(data=request.data)

        if not serializer.is_valid():
            logger.warning("VYRA chat request rejected: invalid payload")
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        question = serializer.validated_data["question"]
        session_id = serializer.validated_data["session_id"]
        client_id = serializer.validated_data["client_id"]
        collection_name = serializer.validated_data["collection_name"]

        try:
            answer = ask_vyra(
                client_id=client_id,
                session_id=session_id,
                question=question,
                collection_name=collection_name,
            )
            return Response(
                {
                    "answer": answer,
                    "client_id": client_id,
                    "session_id": session_id,
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            logger.exception("VYRA chat request failed")
            return Response(
                {"error": "VYRA was unable to process your request."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
