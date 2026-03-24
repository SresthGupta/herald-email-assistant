"""
Auto-archive non-important emails out of the Gmail inbox.

IMPORTANT: DRY_RUN is currently enabled. The archiver will only LOG what it
would archive to ~/Agents/herald-data/archive-suggestions.log but will NOT
actually move any emails. This is intentional until the user supervises and
approves the archive rules.

Set DRY_RUN = False when ready to enable actual archiving.
"""
import os
from datetime import datetime
from pathlib import Path

import httpx
from ..database import get_db


# ============================================================
# DRY RUN MODE: Set to False to enable actual archiving.
# When True, emails are classified but never moved.
# ============================================================
DRY_RUN = True

ARCHIVE_CATEGORIES = {"newsletter", "marketing", "notification", "social", "receipt"}
ARCHIVE_IMPORTANCES = {"low"}

# Log file for archive suggestions
SUGGESTIONS_DIR = Path.home() / "Agents" / "herald-data"
SUGGESTIONS_LOG = SUGGESTIONS_DIR / "archive-suggestions.log"


def _log_suggestion(email: dict, reason: str):
    """Log what would be archived to the suggestions file."""
    SUGGESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = email.get("subject", "(no subject)")[:80]
    sender = email.get("from_address", "unknown")
    category = email.get("category", "uncategorized")
    importance = email.get("importance", "unknown")

    entry = (
        f"[{timestamp}] WOULD ARCHIVE\n"
        f"  Subject: {subject}\n"
        f"  From: {sender}\n"
        f"  Category: {category} | Importance: {importance}\n"
        f"  Reason: {reason}\n"
        f"\n"
    )

    with open(SUGGESTIONS_LOG, "a") as f:
        f.write(entry)


class GmailArchiver:
    BASE_URL = "https://gmail.googleapis.com/gmail/v1"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def archive_message(self, gmail_id: str) -> bool:
        """Remove INBOX label from a message (archives it)."""
        if DRY_RUN:
            return False  # Never actually archive in dry run mode

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.BASE_URL}/users/me/messages/{gmail_id}/modify",
                headers=self.headers,
                json={"removeLabelIds": ["INBOX"]},
            )
            return response.status_code == 200


async def auto_archive_emails(user_id: int, access_token: str, dry_run: bool = None) -> dict:
    """
    Archive emails that match the auto-archive criteria.
    NOTE: Currently forced to DRY_RUN mode. Only logs suggestions.
    Returns counts of what was/would be archived.
    """
    # Force dry_run if global DRY_RUN is True
    if DRY_RUN:
        dry_run = True

    archiver = GmailArchiver(access_token)

    with get_db() as db:
        settings = db.execute(
            "SELECT auto_archive_enabled, auto_archive_categories FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        auto_archive_enabled = True
        if settings:
            row = dict(settings)
            if "auto_archive_enabled" in row and row["auto_archive_enabled"] is not None:
                auto_archive_enabled = bool(row["auto_archive_enabled"])

        if not auto_archive_enabled:
            return {"archived": 0, "skipped": 0, "dry_run": DRY_RUN}

        candidates = db.execute(
            """
            SELECT id, gmail_id, subject, from_address, category, importance
            FROM emails
            WHERE user_id = ? AND archived = 0
            AND (category IN ({}) OR importance = 'low')
            """.format(",".join("?" * len(ARCHIVE_CATEGORIES))),
            (user_id, *ARCHIVE_CATEGORIES),
        ).fetchall()

    suggested = 0
    archived = 0
    skipped = 0

    for row in candidates:
        email_dict = dict(row)

        if DRY_RUN:
            reason = f"category={email_dict.get('category', '?')}, importance={email_dict.get('importance', '?')}"
            _log_suggestion(email_dict, reason)
            suggested += 1
            continue

        success = await archiver.archive_message(row["gmail_id"])
        if success:
            with get_db() as db:
                db.execute(
                    "UPDATE emails SET archived = 1 WHERE id = ?", (row["id"],)
                )
            archived += 1
        else:
            skipped += 1

    if DRY_RUN:
        return {"suggested": suggested, "archived": 0, "skipped": 0, "dry_run": True}

    return {"archived": archived, "skipped": skipped, "dry_run": False}


def is_archivable(email: dict) -> bool:
    """Check if an email should be auto-archived."""
    return (
        email.get("category") in ARCHIVE_CATEGORIES
        or email.get("importance") == "low"
    )
