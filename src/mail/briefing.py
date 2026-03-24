import subprocess
from datetime import date
from database import get_db
from ai.classifier import EmailClassifier


def run_claude(prompt: str) -> str:
    """Run a prompt through the claude CLI and return the output."""
    result = subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip()


async def generate_briefing(user_id: int) -> dict:
    """Generate a daily email briefing using Claude via CLI."""
    today = date.today().isoformat()

    # Check for existing briefing
    with get_db() as db:
        existing = db.execute(
            "SELECT * FROM briefings WHERE user_id = ? AND date = ?",
            (user_id, today),
        ).fetchone()
        if existing:
            return dict(existing)

    # Gather unread, non-high-importance emails not yet in a briefing
    with get_db() as db:
        emails = db.execute(
            """
            SELECT from_name, from_address, subject, snippet, date, category, importance
            FROM emails
            WHERE user_id = ? AND included_in_briefing = 0
            ORDER BY id DESC LIMIT 50
            """,
            (user_id,),
        ).fetchall()
        emails = [dict(e) for e in emails]

    if not emails:
        return {
            "content": "<p>Your inbox is quiet today. Nothing new to report.</p>",
            "email_count": 0,
            "important_count": 0,
            "date": today,
        }

    important_emails = [e for e in emails if e["importance"] == "high"]

    # Build prompt
    email_text = ""
    for e in emails[:40]:
        email_text += f"- From: {e['from_name']} <{e['from_address']}>\n"
        email_text += f"  Subject: {e['subject']}\n"
        email_text += f"  Preview: {e['snippet'][:150]}\n"
        email_text += f"  Category: {e['category']} | Importance: {e['importance']}\n\n"

    prompt = f"""You are Herald, an AI email assistant. Generate a clean, scannable daily email briefing.

Today's date: {today}
Total emails to brief: {len(emails)}
High importance: {len(important_emails)}

Emails:
{email_text}

Create a briefing with these sections:
1. A one-sentence "Today at a glance" summary
2. "Needs Attention" - list only high importance items (if any), with sender, subject, and one-line description
3. "Everything Else" - group remaining emails by category with brief summaries
4. A friendly closing note

Format as clean HTML using <p>, <ul>, <li>, <strong>, <span> tags only.
Keep it tight and scannable - this should take under 30 seconds to read.
Use a friendly, professional tone. No em dashes. No markdown."""

    content = run_claude(prompt)

    if not content:
        content = "<p>Unable to generate briefing. Please try again.</p>"

    # Save briefing
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO briefings (user_id, content, email_count, important_count, date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, content, len(emails), len(important_emails), today),
        )
        briefing_id = cursor.lastrowid

        # Mark emails as included
        db.execute(
            "UPDATE emails SET included_in_briefing = 1 WHERE user_id = ? AND included_in_briefing = 0",
            (user_id,),
        )

    return {
        "id": briefing_id,
        "content": content,
        "email_count": len(emails),
        "important_count": len(important_emails),
        "date": today,
    }


def get_recent_briefings(user_id: int, limit: int = 7) -> list[dict]:
    """Get recent briefings for a user."""
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, date, email_count, important_count, created_at
            FROM briefings WHERE user_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_briefing_by_id(user_id: int, briefing_id: int) -> dict | None:
    """Get a specific briefing."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM briefings WHERE id = ? AND user_id = ?",
            (briefing_id, user_id),
        ).fetchone()
    return dict(row) if row else None
