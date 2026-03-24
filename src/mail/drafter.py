import subprocess
from database import get_db
from mail.gmail_client import GmailClient


def run_claude(prompt: str) -> str:
    """Run a prompt through the claude CLI and return the output."""
    result = subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip()


async def draft_reply(user_id: int, email_id: int, access_token: str) -> dict:
    """Generate a draft reply for an email using the user's writing style."""
    with get_db() as db:
        email_row = db.execute(
            "SELECT * FROM emails WHERE id = ? AND user_id = ?",
            (email_id, user_id),
        ).fetchone()

        if not email_row:
            raise ValueError("Email not found")

        email_data = dict(email_row)

        # Load writing style samples
        samples = db.execute(
            "SELECT sample_text FROM style_samples WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,),
        ).fetchall()
        style_samples = [s["sample_text"] for s in samples]

        # Load user info
        user = db.execute(
            "SELECT name, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        user_name = user["name"] if user else "the user"

    style_context = ""
    if style_samples:
        style_context = "Here are examples of how this person writes emails:\n\n"
        for i, sample in enumerate(style_samples[:5], 1):
            style_context += f"Example {i}:\n{sample[:300]}\n\n"
    else:
        style_context = "No writing samples available. Use a clear, professional but friendly tone."

    prompt = f"""You are a personal email assistant helping {user_name} draft a reply.

Original email:
From: {email_data['from_name']} <{email_data['from_address']}>
Subject: {email_data['subject']}
Body: {email_data['body'][:1500]}

{style_context}

Write a natural, helpful reply in the sender's voice. Guidelines:
- Match their writing style from the examples above
- Be concise and direct
- Sound human, not like AI wrote it
- Do not use em dashes
- Do not add a subject line, just the email body
- Sign off naturally with just their first name or however they usually sign emails

Reply body only, no subject line:"""

    draft_body = run_claude(prompt)
    if not draft_body:
        draft_body = "Thank you for your email. I'll get back to you shortly."

    reply_subject = f"Re: {email_data['subject']}"

    # Save draft to DB
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO drafts (user_id, email_id, subject, to_address, body, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (
                user_id,
                email_id,
                reply_subject,
                email_data["from_address"],
                draft_body,
            ),
        )
        draft_id = cursor.lastrowid

    return {
        "id": draft_id,
        "subject": reply_subject,
        "to": email_data["from_address"],
        "body": draft_body,
        "email_id": email_id,
    }


async def push_draft_to_gmail(user_id: int, draft_id: int, access_token: str) -> dict:
    """Push a pending draft to Gmail drafts folder."""
    with get_db() as db:
        draft = db.execute(
            "SELECT * FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        ).fetchone()
        if not draft:
            raise ValueError("Draft not found")
        draft = dict(draft)

    client = GmailClient(access_token)
    gmail_draft = await client.create_draft(
        to=draft["to_address"],
        subject=draft["subject"],
        body=draft["body"],
        reply_to_id=None,
    )

    gmail_draft_id = gmail_draft.get("id", "")

    with get_db() as db:
        db.execute(
            "UPDATE drafts SET gmail_draft_id = ?, status = 'pushed' WHERE id = ?",
            (gmail_draft_id, draft_id),
        )

    return {"gmail_draft_id": gmail_draft_id, "status": "pushed"}


def get_pending_drafts(user_id: int) -> list[dict]:
    """Get all pending drafts for a user."""
    with get_db() as db:
        rows = db.execute(
            """
            SELECT d.*, e.from_name as original_sender, e.subject as original_subject
            FROM drafts d
            LEFT JOIN emails e ON d.email_id = e.id
            WHERE d.user_id = ? AND d.status = 'pending'
            ORDER BY d.id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_draft(user_id: int, draft_id: int) -> bool:
    """Delete a draft."""
    with get_db() as db:
        db.execute(
            "DELETE FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        )
    return True
