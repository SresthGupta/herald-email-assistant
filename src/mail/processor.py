from database import get_db
from mail.gmail_client import GmailClient
from ai.classifier import EmailClassifier
from rules.engine import RulesEngine
from config import MAX_EMAILS_TO_PROCESS


async def sync_and_process_emails(user_id: int, access_token: str) -> dict:
    """Fetch new emails from Gmail, classify them, and apply rules."""
    client = GmailClient(access_token)
    classifier = EmailClassifier()

    # Load existing gmail IDs to avoid reprocessing
    with get_db() as db:
        existing = {
            row["gmail_id"]
            for row in db.execute(
                "SELECT gmail_id FROM emails WHERE user_id = ?", (user_id,)
            ).fetchall()
        }
        rules = db.execute(
            "SELECT * FROM rules WHERE user_id = ? AND active = 1", (user_id,)
        ).fetchall()
        rules_list = [dict(r) for r in rules]

    engine = RulesEngine(rules_list)

    messages_meta = await client.list_messages(
        max_results=MAX_EMAILS_TO_PROCESS,
        query="in:inbox -category:promotions -category:social",
    )

    new_count = 0
    for meta in messages_meta:
        gmail_id = meta["id"]
        if gmail_id in existing:
            continue

        raw = await client.get_message(gmail_id)
        parsed = client.parse_message(raw)

        importance, category = await classifier.classify(parsed)
        rule_override = engine.apply(parsed)
        if rule_override:
            importance = rule_override.get("importance", importance)
            category = rule_override.get("category", category)

        with get_db() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO emails
                (user_id, gmail_id, thread_id, from_address, from_name,
                 subject, snippet, body, date, is_read, importance, category, processed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user_id,
                    parsed["id"],
                    parsed["thread_id"],
                    parsed["from_address"],
                    parsed["from_name"],
                    parsed["subject"],
                    parsed["snippet"],
                    parsed["body"][:4000],
                    parsed["date"],
                    1 if parsed["is_read"] else 0,
                    importance,
                    category,
                ),
            )
        new_count += 1

    return {"synced": new_count, "total_checked": len(messages_meta)}


def get_inbox_summary(user_id: int) -> dict:
    """Get a quick summary of the inbox state."""
    with get_db() as db:
        total = db.execute(
            "SELECT COUNT(*) as c FROM emails WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]

        important = db.execute(
            "SELECT COUNT(*) as c FROM emails WHERE user_id = ? AND importance = 'high'",
            (user_id,),
        ).fetchone()["c"]

        unread = db.execute(
            "SELECT COUNT(*) as c FROM emails WHERE user_id = ? AND is_read = 0",
            (user_id,),
        ).fetchone()["c"]

        recent = db.execute(
            """
            SELECT from_name, subject, date, importance, category, snippet
            FROM emails WHERE user_id = ?
            ORDER BY id DESC LIMIT 10
            """,
            (user_id,),
        ).fetchall()

        pending_drafts = db.execute(
            "SELECT COUNT(*) as c FROM drafts WHERE user_id = ? AND status = 'pending'",
            (user_id,),
        ).fetchone()["c"]

    return {
        "total": total,
        "important": important,
        "unread": unread,
        "pending_drafts": pending_drafts,
        "recent_emails": [dict(r) for r in recent],
    }
