# chatbot/services/gmail_service.py

import base64
from email.mime.text import MIMEText

from django.conf import settings

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def send_gmail_email(*, recipient, subject, message):
    """
    Send a plain-text email through Gmail API using the saved OAuth token.
    Returns the Gmail message ID when successful.
    """
    token_path = settings.BASE_DIR / "gmail_token.json"

    credentials = Credentials.from_authorized_user_file(
        str(token_path),
        scopes=[GMAIL_SEND_SCOPE],
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json(), encoding="utf-8")

    if not credentials.valid:
        raise RuntimeError(
            "Gmail OAuth credentials are invalid. "
            "Run the Gmail OAuth authorization flow again."
        )

    email = MIMEText(message, "plain", "utf-8")
    email["to"] = recipient
    email["from"] = settings.GMAIL_SENDER_EMAIL
    email["subject"] = subject

    encoded_message = base64.urlsafe_b64encode(
        email.as_bytes()
    ).decode("utf-8")

    gmail = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    result = (
        gmail.users()
        .messages()
        .send(
            userId="me",
            body={"raw": encoded_message},
        )
        .execute()
    )

    message_id = result.get("id")
    if not message_id:
        raise RuntimeError("Gmail API returned no message ID.")


  