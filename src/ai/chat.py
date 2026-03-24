"""
AI chat interface: answer questions about the user's email using Claude via CLI.
"""
import json
import subprocess
from database import get_db


SYSTEM_PROMPT = """You are Herald, a helpful AI email assistant. You have access to the user's email data and answer questions about their emails.

When answering:
- Be concise and direct
- Reference specific emails when relevant (include sender, subject, and date)
- Format lists with bullet points
- If asked to find something specific, say how many results you found
- Do not make up emails that aren't in the context
- No em dashes"""


def run_claude(prompt: str) -> str:
    """Run a prompt through the claude CLI and return the output."""
    result = subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip()


async def chat_with_emails(user_id: int, message: str, conversation_history: list[dict] = None) -> dict:
    """
    Answer a question about the user's emails using Claude via CLI.
    Returns the response and any relevant email IDs found.
    """
    # Search emails relevant to the query
    relevant_emails = search_emails_for_context(user_id, message)

    # Build email context
    email_context = build_email_context(relevant_emails)

    # Build conversation history text
    history_text = ""
    if conversation_history:
        for msg in conversation_history[-6:]:  # Include last 6 turns for context
            role = "User" if msg["role"] == "user" else "Herald"
            history_text += f"{role}: {msg['content']}\n\n"

    prompt = f"""{SYSTEM_PROMPT}

{history_text}Relevant emails from inbox:
{email_context}

User question: {message}

Answer:"""

    answer = run_claude(prompt)

    if not answer:
        answer = "I was unable to process your request. Please try again."

    return {
        "response": answer,
        "emails": [
            {
                "id": e["id"],
                "gmail_id": e["gmail_id"],
                "subject": e["subject"],
                "from_name": e["from_name"],
                "from_address": e["from_address"],
                "date": e["date"],
                "importance": e["importance"],
                "category": e["category"],
            }
            for e in relevant_emails[:5]
        ],
    }


def search_emails_for_context(user_id: int, query: str, limit: int = 20) -> list[dict]:
    """
    Find emails relevant to a query using simple keyword matching.
    Returns a list of email dicts.
    """
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 3]

    with get_db() as db:
        # Try to find emails matching the query terms
        if query_words:
            conditions = []
            params = [user_id]
            for word in query_words[:5]:
                conditions.append(
                    "(LOWER(subject) LIKE ? OR LOWER(from_name) LIKE ? OR LOWER(from_address) LIKE ? OR LOWER(snippet) LIKE ?)"
                )
                like = f"%{word}%"
                params.extend([like, like, like, like])

            where = " AND ".join(conditions) if conditions else "1=1"
            query_sql = f"""
                SELECT id, gmail_id, from_name, from_address, subject, snippet, body,
                       date, importance, category, is_read, archived
                FROM emails
                WHERE user_id = ? AND ({where})
                ORDER BY id DESC LIMIT ?
            """
            params.append(limit)
            rows = db.execute(query_sql, params).fetchall()
        else:
            rows = db.execute(
                """SELECT id, gmail_id, from_name, from_address, subject, snippet, body,
                          date, importance, category, is_read, archived
                   FROM emails WHERE user_id = ? ORDER BY id DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()

    return [dict(r) for r in rows]


def build_email_context(emails: list[dict]) -> str:
    """Build a text representation of emails for AI context."""
    if not emails:
        return "No emails found matching your query."

    lines = []
    for e in emails[:15]:
        lines.append(
            f"[ID:{e['id']}] From: {e['from_name']} <{e['from_address']}> | "
            f"Subject: {e['subject']} | Date: {e['date']} | "
            f"Importance: {e['importance']} | Category: {e['category']}"
        )
        if e.get("snippet"):
            lines.append(f"  Preview: {e['snippet'][:200]}")
        lines.append("")

    return "\n".join(lines)


def get_chat_history(user_id: int, limit: int = 20) -> list[dict]:
    """Get recent chat history for a user."""
    with get_db() as db:
        rows = db.execute(
            """SELECT * FROM chat_messages WHERE user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


def save_chat_message(user_id: int, role: str, content: str, email_ids: list[int] = None):
    """Save a chat message to the database."""
    with get_db() as db:
        db.execute(
            "INSERT INTO chat_messages (user_id, role, content, email_ids) VALUES (?, ?, ?, ?)",
            (user_id, role, content, json.dumps(email_ids or [])),
        )


def clear_chat_history(user_id: int):
    """Clear all chat history for a user."""
    with get_db() as db:
        db.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
