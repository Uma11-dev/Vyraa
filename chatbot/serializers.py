from rest_framework import serializers


class ChatSerializer(serializers.Serializer):
    """
    Validates incoming VYRA chat requests.
    """

    client_id = serializers.CharField(
        max_length=100,
        required=True
    )

    session_id = serializers.CharField(
        max_length=100,
        required=True
    )

    question = serializers.CharField(
        required=True,
        allow_blank=False
    )

    collection_name = serializers.CharField(
        max_length=255,
        required=True
    )