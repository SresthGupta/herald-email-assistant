"""
One-click unsubscribe: parse List-Unsubscribe headers and body links,
then trigger the unsubscribe action.
"""
import re
import httpx
from mail.gmail_client import GmailClient
from database import get_db


def extract_unsubscribe_url(raw_message: dict) -> str | None:
    """
    Extract an unsubscribe URL from a Gmail message.
    Checks List-Unsubscribe header first, then body.
    """
    headers = {
        h["name"].lower(): h["value"]
        for h in raw_message.get("payload", {}).get("headers", [])
    }

    # Check List-Unsubscribe header (RFC 2369)
    list_unsub = headers.get("list-unsubscribe", "")
    if list_unsub:
        # Format: <https://...>, <mailto:...> - prefer HTTPS
        urls = re.findall(r'<(https?://[^>]+)>', list_unsub)
        if urls:
            return urls[0]
        # Fall back to mailto
        mailto = re.findall(r'<(mailto:[^>]+)>', list_unsub)
        if mailto:
            return mailto[0]

    return None


def extract_unsubscribe_from_body(body: str) -> str | None:
    """Find an unsubscribe link in the email body."""
    patterns = [
        r'href=["\']?(https?://[^"\'>\s]*unsubscribe[^"\'>\s]*)',
        r'https?://[^\s<>"]*unsubscribe[^\s<>"]*',
        r'href=["\']?(https?://[^"\'>\s]*optout[^"\'>\s]*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            url = match.group(1) if match.lastindex else match.group(0)
            if len(url) < 500:
                return url
    return None


async def perform_unsubscribe(user_id: int, email_id: int, access_token: str) -> dict:
    """
    Perform the unsubscribe action for a given email.
    Returns status and the URL used.
    """
    with get_db() as db:
        email_row = db.execute(
            "SELECT * FROM emails WHERE id = ? AND user_id = ?",
            (email_id, user_id),
        ).fetchone()

        if not email_row:
            return {"success": False, "error": "Email not found"}

        email_data = dict(email_row)

    # Fetch full raw message to check headers
    client = GmailClient(access_token)
    try:
        raw = await client.get_message(email_data["gmail_id"], format="full")
    except Exception as e:
        return {"success": False, "error": str(e)}

    # Try header first, then body
    unsub_url = extract_unsubscribe_url(raw)
    if not unsub_url and email_data.get("body"):
        unsub_url = extract_unsubscribe_from_body(email_data["body"])

    if not unsub_url:
        return {
            "success": False,
            "error": "No unsubscribe link found in this email",
            "email_id": email_id,
        }

    # Handle mailto: unsubscribe
    if unsub_url.startswith("mailto:"):
        return {
            "success": True,
            "method": "mailto",
            "url": unsub_url,
            "message": "Open your email client to complete unsubscription",
        }

    # For HTTP URLs, make a GET request to trigger unsubscribe
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http_client:
            response = await http_client.get(
                unsub_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Herald/1.0)"},
            )
            success = response.status_code < 400
    except Exception as e:
        # Still return the URL so user can click it
        return {
            "success": False,
            "method": "http",
            "url": unsub_url,
            "error": str(e),
            "message": "Could not auto-unsubscribe. Click the link to unsubscribe manually.",
        }

    # Mark as unsubscribed in DB
    with get_db() as db:
        db.execute(
            "UPDATE emails SET unsubscribed = 1 WHERE id = ? AND user_id = ?",
            (email_id, user_id),
        )

    return {
        "success": success,
        "method": "http",
        "url": unsub_url,
        "message": "Unsubscribed successfully!" if success else "Unsubscribe may have failed",
    }


def get_gmail_url(gmail_id: str) -> str:
    """Get the direct Gmail URL for an email."""
    return f"https://mail.google.com/mail/u/0/#inbox/{gmail_id}"
