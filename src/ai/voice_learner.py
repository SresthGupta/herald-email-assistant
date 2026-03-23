"""
Learn and store the user's email writing style from their sent emails.
"""
import anthropic
from database import get_db
from mail.gmail_client import GmailClient
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


async def learn_style_from_sent(user_id: int, access_token: str, max_samples: int = 20) -> int:
    """Fetch sent emails and extract style samples."""
    client = GmailClient(access_token)

    sent_messages = await client.list_messages(
        max_results=max_samples,
        label_ids=["SENT"],
    )

    samples_added = 0
    for meta in sent_messages[:max_samples]:
        raw = await client.get_message(meta["id"])
        parsed = client.parse_message(raw)
        body = parsed.get("body", "").strip()

        # Only use substantive emails (not auto-replies etc.)
        if len(body) < 50 or len(body) > 2000:
            continue

        with get_db() as db:
            existing = db.execute(
                "SELECT id FROM style_samples WHERE user_id = ? AND sample_text = ?",
                (user_id, body[:500]),
            ).fetchone()

            if not existing:
                db.execute(
                    "INSERT INTO style_samples (user_id, sample_text, context) VALUES (?, ?, ?)",
                    (user_id, body[:500], f"Subject: {parsed.get('subject', '')}"),
                )
                samples_added += 1

    return samples_added


def get_style_summary(user_id: int) -> str:
    """Generate a text summary of the user's writing style."""
    with get_db() as db:
        samples = db.execute(
            "SELECT sample_text FROM style_samples WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,),
        ).fetchall()

    if not samples:
        return "No writing samples collected yet."

    if not ANTHROPIC_API_KEY:
        return f"{len(samples)} writing samples collected."

    samples_text = "\n\n---\n\n".join(s["sample_text"] for s in samples[:8])

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Describe this person's email writing style in 2-3 sentences. Focus on tone, formality, length, and any distinctive patterns.

Email samples:
{samples_text}

Style description:"""
        }],
    )

    return message.content[0].text.strip()


def get_sample_count(user_id: int) -> int:
    """Get the number of style samples for a user."""
    with get_db() as db:
        result = db.execute(
            "SELECT COUNT(*) as c FROM style_samples WHERE user_id = ?", (user_id,)
        ).fetchone()
    return result["c"]
