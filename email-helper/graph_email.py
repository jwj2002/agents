"""Microsoft Graph email helper for VitalAILabs agent communication.

Handles both sending new emails and threaded replies correctly.
Uses the /messages/{id}/reply endpoint for replies (not sendMail with RE: prefix).

Usage:
    from graph_email import GraphMailClient

    client = GraphMailClient()  # loads credentials from env or defaults

    # New email
    client.send_email(
        to="ai-coder@vital-enterprises.com",
        subject="jbox6 status update",
        body="<p>Setup complete.</p>",
    )

    # Threaded reply
    client.reply_email(
        to="ai-coder@vital-enterprises.com",
        body="<p>Thanks, confirmed.</p>",
        original_subject="jbox6 status update",
    )

    # Read inbox
    messages = client.read_inbox(top=10)
    for m in messages:
        print(f"{m['from']['emailAddress']['address']}: {m['subject']}")
"""
import json
import os

import httpx
from azure.identity import ClientSecretCredential

# Credentials loaded from environment variables only.
# Set these in ~/.claude/.env or export them in your shell:
#   GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_SENDER


class GraphMailClient:
    """Microsoft Graph API email client with proper threading support."""

    def __init__(
        self,
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        sender: str = "",
    ):
        self.tenant_id = tenant_id or os.environ.get("GRAPH_TENANT_ID", "")
        self.client_id = client_id or os.environ.get("GRAPH_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("GRAPH_CLIENT_SECRET", "")
        self.sender = sender or os.environ.get("GRAPH_SENDER", "")

        if not all([self.tenant_id, self.client_id, self.client_secret, self.sender]):
            raise ValueError(
                "Missing Graph API credentials. Set environment variables: "
                "GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_SENDER"
            )
        self._token = None

    def _get_token(self) -> str:
        """Get or refresh the bearer token."""
        cred = ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        self._token = cred.get_token("https://graph.microsoft.com/.default").token
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _base_url(self) -> str:
        return f"https://graph.microsoft.com/v1.0/users/{self.sender}"

    # ------------------------------------------------------------------
    # Send new email (no existing thread)
    # ------------------------------------------------------------------

    def send_email(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        content_type: str = "HTML",
    ) -> int:
        """Send a new email. Returns HTTP status code (202 = success)."""
        if isinstance(to, str):
            to = [to]
        to_recipients = [{"emailAddress": {"address": a}} for a in to]

        message = {
            "subject": subject,
            "body": {"contentType": content_type, "content": body},
            "toRecipients": to_recipients,
        }

        if cc:
            if isinstance(cc, str):
                cc = [cc]
            message["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc]

        payload = {"message": message, "saveToSentItems": "true"}

        r = httpx.post(
            f"{self._base_url()}/sendMail",
            headers=self._headers(),
            content=json.dumps(payload),
        )
        return r.status_code

    # ------------------------------------------------------------------
    # Reply to existing thread
    # ------------------------------------------------------------------

    def reply_email(
        self,
        to: str | list[str],
        body: str,
        original_subject: str = "",
        message_id: str = "",
        search_folder: str = "sentItems",
        cc: str | list[str] | None = None,
    ) -> int:
        """Reply to an existing email thread. Returns HTTP status code (202 = success).

        Finds the original message by subject (or uses message_id directly),
        then uses the /messages/{id}/reply endpoint for proper threading.

        Args:
            to: Recipient(s) for the reply.
            body: HTML body for the reply.
            original_subject: Subject of the original email to find.
            message_id: Graph message ID (skips search if provided).
            search_folder: Where to search — 'sentItems' for emails you sent,
                          'inbox' for emails you received.
            cc: Optional CC recipient(s).
        """
        if not message_id:
            if not original_subject:
                raise ValueError("Either message_id or original_subject is required")
            message_id = self._find_message_id(original_subject, search_folder)

        if isinstance(to, str):
            to = [to]

        payload: dict = {
            "message": {
                "toRecipients": [{"emailAddress": {"address": a}} for a in to],
            },
            "comment": body,
        }

        if cc:
            if isinstance(cc, str):
                cc = [cc]
            payload["message"]["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc]

        r = httpx.post(
            f"{self._base_url()}/messages/{message_id}/reply",
            headers=self._headers(),
            content=json.dumps(payload),
        )
        return r.status_code

    # ------------------------------------------------------------------
    # Read inbox
    # ------------------------------------------------------------------

    def read_inbox(self, top: int = 10, unread_only: bool = False) -> list[dict]:
        """Read messages from inbox.

        Returns list of message dicts with subject, from, receivedDateTime, bodyPreview.
        """
        url = (
            f"{self._base_url()}/messages"
            f"?$top={top}"
            f"&$select=id,subject,from,receivedDateTime,bodyPreview,isRead"
            f"&$orderby=receivedDateTime desc"
        )
        if unread_only:
            url += "&$filter=isRead eq false"

        r = httpx.get(url, headers=self._headers())
        if r.status_code != 200:
            return []
        return r.json().get("value", [])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_message_id(self, subject: str, folder: str = "sentItems") -> str:
        """Find a message ID by subject in the specified folder."""
        # Use $search instead of $filter — more reliable with special characters
        # $search uses KQL syntax
        safe_subject = subject.replace('"', '\\"')
        url = (
            f"{self._base_url()}/mailFolders/{folder}/messages"
            f'?$search="subject:{safe_subject}"'
            f"&$select=id,subject"
            f"&$top=5"
        )
        r = httpx.get(url, headers=self._headers())

        # Fallback: fetch recent messages and match locally
        if r.status_code != 200:
            url = (
                f"{self._base_url()}/mailFolders/{folder}/messages"
                f"?$select=id,subject"
                f"&$top=25"
                f"&$orderby=receivedDateTime desc"
            )
            r = httpx.get(url, headers=self._headers())
            if r.status_code != 200:
                raise RuntimeError(f"Failed to search {folder}: {r.status_code} {r.text[:200]}")
            messages = [
                m for m in r.json().get("value", [])
                if subject.lower() in m.get("subject", "").lower()
            ]
        else:
            messages = r.json().get("value", [])

        if not messages:
            raise ValueError(
                f"No message found with subject '{subject}' in {folder}. "
                f"Try search_folder='inbox' if replying to a received message."
            )
        return messages[0]["id"]
