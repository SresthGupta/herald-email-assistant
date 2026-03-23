"""
Auto-archive non-important emails out of the Gmail inbox.
Archived emails are still stored locally and included in briefings.
"""
import httpx
from database import get_db


ARCHIVE_CATEGORIES = {"newsletter", "marketing", "notification", "social", "receipt"}
ARCHIVE_IMPORTANCES = {"low"}


class GmailArchiver:
    BASE_URL = "https://gmail.googleapis.com/gmail/v1"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def archive_message(self, gmail_id: str) -> bool:
        """Remove INBOX label from a message (archives it)."""
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.BASE_URL}/users/me/messages/{gmail_id}/modify",
                headers=self.headers,
                json={"removeLabelIds": ["INBOX"]},
            )
            return response.status_code == 200


async def auto_archive_emails(user_id: int, access_token: str, dry_run: bool = False) -> dict:
    """
    Archive emails that match the auto-archive criteria.
    Returns counts of what was archived.
    """
    archiver = GmailArchiver(access_token)

    with get_db() as db:
        # Load user's auto-archive settings
        settings = db.execute(
            "SELECT auto_archive_enabled, auto_archive_categories FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        # Check if column exists (may not in older DBs) and get setting
        auto_archive_enabled = True
        archive_categories = ARCHIVE_CATEGORIES

        if settings:
            row = dict(settings)
            if "auto_archive_enabled" in row and row["auto_archive_enabled"] is not None:
                auto_archive_enabled = bool(row["auto_archive_enabled"])

        if not auto_archive_enabled:
            return {"archived": 0, "skipped": 0}

        # Find emails eligible for archiving
        candidates = db.execute(
            """
            SELECT id, gmail_id, category, importance
            FROM emails
            WHERE user_id = ? AND archived = 0
            AND (category IN ({}) OR importance = 'low')
            """.format(",".join("?" * len(ARCHIVE_CATEGORIES))),
            (user_id, *ARCHIVE_CATEGORIES),
        ).fetchall()

    archived = 0
    skipped = 0

    for row in candidates:
        if dry_run:
            archived += 1
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

    return {"archived": archived, "skipped": skipped}


def is_archivable(email: dict) -> bool:
    """Check if an email should be auto-archived."""
    return (
        email.get("category") in ARCHIVE_CATEGORIES
        or email.get("importance") == "low"
    )
