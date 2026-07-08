import base64
from email.message import EmailMessage


class GmailClient:
    def __init__(self, service):
        self._service = service

    def search_messages(self, query: str, limit: int = 10) -> list[dict]:
        listing = self._service.users().messages().list(
            userId="me", q=query, maxResults=limit
        ).execute()

        results = []
        for ref in listing.get("messages", []):
            full = self._service.users().messages().get(
                userId="me",
                id=ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            results.append({
                "from_": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": full.get("snippet", ""),
            })
        return results

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        created = self._service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        return {"draft_id": created["id"], "to": to, "subject": subject}
