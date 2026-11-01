
import base64
import os
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent
CLIENT_FILE = BASE_DIR / "gmail_oauth_client.json"
TOKEN_FILE = BASE_DIR / "gmail_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SENDER = "lunas.sanctumassist@gmail.com"


def main():
    if not CLIENT_FILE.exists():
        raise FileNotFoundError(
            f"OAuth credentials not found: {CLIENT_FILE}"
        )

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())
        os.chmod(TOKEN_FILE, 0o600)

    service = build("gmail", "v1", credentials=creds)

    message = EmailMessage()
    message["To"] = SENDER
    message["From"] = SENDER
    message["Subject"] = "VYRA Gmail API test"
    message.set_content(
        "Success! VYRA can send email using the Gmail API."
    )

    encoded = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    result = service.users().messages().send(
        userId="me",
        body={"raw": encoded},
    ).execute()

    print("Email accepted by Gmail API.")
    print("Message ID:", result.get("id"))


if __name__ == "__main__":
    main()
