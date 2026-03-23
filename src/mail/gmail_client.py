import base64
from typing import Optional
import httpx


class GmailClient:
    """Wrapper around the Gmail REST API."""

    BASE_URL = "https://gmail.googleapis.com/gmail/v1"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def _get(self, path: str, params: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                params=params or {},
            )
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, json_data: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                json=json_data,
            )
            response.raise_for_status()
            return response.json()

    async def list_messages(
        self,
        max_results: int = 50,
        query: str = "",
        label_ids: list = None,
    ) -> list[dict]:
        """List messages matching a query."""
        params = {"maxResults": max_results}
        if query:
            params["q"] = query
        if label_ids:
            params["labelIds"] = label_ids

        data = await self._get("/users/me/messages", params)
        return data.get("messages", [])

    async def get_message(self, message_id: str, format: str = "full") -> dict:
        """Get a specific message by ID."""
        return await self._get(
            f"/users/me/messages/{message_id}",
            {"format": format},
        )

    async def get_thread(self, thread_id: str) -> dict:
        """Get a full email thread."""
        return await self._get(f"/users/me/threads/{thread_id}")

    async def list_labels(self) -> list[dict]:
        """List all Gmail labels."""
        data = await self._get("/users/me/labels")
        return data.get("labels", [])

    async def create_draft(self, to: str, subject: str, body: str, reply_to_id: str = None) -> dict:
        """Create a draft email."""
        message_parts = [
            f"To: {to}",
            f"Subject: {subject}",
            "Content-Type: text/plain; charset=utf-8",
            "",
            body,
        ]
        raw_message = "\n".join(message_parts)

        if reply_to_id:
            original = await self.get_message(reply_to_id)
            thread_id = original.get("threadId")
            message_id_header = self._get_header(original, "Message-ID")
            message_parts.insert(-2, f"In-Reply-To: {message_id_header}")
            message_parts.insert(-2, f"References: {message_id_header}")
            raw_message = "\n".join(message_parts)

        encoded = base64.urlsafe_b64encode(raw_message.encode()).decode()
        payload = {"message": {"raw": encoded}}
        if reply_to_id:
            payload["message"]["threadId"] = thread_id

        return await self._post("/users/me/drafts", payload)

    def parse_message(self, raw_message: dict) -> dict:
        """Parse a raw Gmail API message into a clean dict."""
        headers = {h["name"]: h["value"] for h in raw_message.get("payload", {}).get("headers", [])}

        body = self._extract_body(raw_message.get("payload", {}))

        return {
            "id": raw_message.get("id"),
            "thread_id": raw_message.get("threadId"),
            "from_address": self._parse_email_address(headers.get("From", "")),
            "from_name": self._parse_display_name(headers.get("From", "")),
            "to_address": headers.get("To", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "snippet": raw_message.get("snippet", ""),
            "body": body,
            "label_ids": raw_message.get("labelIds", []),
            "is_read": "UNREAD" not in raw_message.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
        """Recursively extract the plain text body from a message payload."""
        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data", "")

        if mime_type == "text/plain" and body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

        parts = payload.get("parts", [])
        for part in parts:
            result = self._extract_body(part)
            if result:
                return result

        if mime_type == "text/html" and body_data:
            html = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            return self._strip_html(html)

        return ""

    def _strip_html(self, html: str) -> str:
        """Very basic HTML stripping."""
        import re
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:2000]

    def _parse_email_address(self, from_header: str) -> str:
        """Extract just the email address from a From header."""
        import re
        match = re.search(r"<([^>]+)>", from_header)
        if match:
            return match.group(1)
        return from_header.strip()

    def _parse_display_name(self, from_header: str) -> str:
        """Extract the display name from a From header."""
        import re
        match = re.match(r'^"?([^"<]+)"?\s*<', from_header)
        if match:
            return match.group(1).strip()
        return self._parse_email_address(from_header)

    def _get_header(self, message: dict, name: str) -> str:
        """Get a specific header from a message."""
        headers = message.get("payload", {}).get("headers", [])
        for h in headers:
            if h["name"].lower() == name.lower():
                return h["value"]
        return ""
