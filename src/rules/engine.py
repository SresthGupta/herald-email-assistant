"""
Plain-language rules engine powered by Claude.
Rules are stored as natural language and converted to structured JSON for fast matching.
"""
import json
import re
import anthropic
from database import get_db
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


class RulesEngine:
    """Apply user-defined plain-language rules to emails."""

    def __init__(self, rules: list[dict]):
        self.rules = rules

    def apply(self, email: dict) -> dict | None:
        """
        Apply all rules to an email and return any override dict.
        Returns None if no rule matched, or dict with 'importance' and/or 'category'.
        """
        for rule in self.rules:
            rule_json = rule.get("rule_json")
            if not rule_json:
                continue
            try:
                parsed = json.loads(rule_json)
                result = self._match_rule(parsed, email)
                if result:
                    return result
            except (json.JSONDecodeError, KeyError):
                continue
        return None

    def _match_rule(self, rule: dict, email: dict) -> dict | None:
        """Match a structured rule against an email."""
        conditions = rule.get("conditions", [])
        actions = rule.get("actions", {})

        for condition in conditions:
            field = condition.get("field", "")
            operator = condition.get("operator", "contains")
            value = condition.get("value", "").lower()

            email_value = self._get_field(email, field).lower()

            if operator == "contains":
                if value not in email_value:
                    return None
            elif operator == "equals":
                if email_value != value:
                    return None
            elif operator == "starts_with":
                if not email_value.startswith(value):
                    return None
            elif operator == "ends_with":
                if not email_value.endswith(value):
                    return None
            elif operator == "not_contains":
                if value in email_value:
                    return None

        return actions if actions else None

    def _get_field(self, email: dict, field: str) -> str:
        field_map = {
            "from": email.get("from_address", ""),
            "sender": email.get("from_address", ""),
            "from_domain": "@" + email.get("from_address", "").split("@")[-1],
            "subject": email.get("subject", ""),
            "body": email.get("body", ""),
            "snippet": email.get("snippet", ""),
        }
        return str(field_map.get(field, ""))


async def parse_rule_to_json(rule_text: str) -> str | None:
    """
    Use Claude to convert a plain-language rule into structured JSON.
    Returns JSON string or None on failure.
    """
    if not ANTHROPIC_API_KEY:
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Convert this email rule to JSON. Return only valid JSON.

Rule: "{rule_text}"

JSON format:
{{
  "conditions": [
    {{"field": "from|subject|body|from_domain", "operator": "contains|equals|starts_with|ends_with|not_contains", "value": "..."}}
  ],
  "actions": {{
    "importance": "high|medium|low",
    "category": "personal|work|finance|newsletter|notification|marketing|social|travel|receipt|general"
  }}
}}

Examples:
- "Mark emails from @company.com as important" -> {{"conditions": [{{"field": "from_domain", "operator": "contains", "value": "@company.com"}}], "actions": {{"importance": "high"}}}}
- "Archive all marketing emails" -> {{"conditions": [{{"field": "subject", "operator": "contains", "value": "unsubscribe"}}], "actions": {{"importance": "low", "category": "marketing"}}}}
- "Emails with invoice in subject are finance" -> {{"conditions": [{{"field": "subject", "operator": "contains", "value": "invoice"}}], "actions": {{"category": "finance"}}}}

JSON:"""

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    match = re.search(r'\{[\s\S]+\}', text)
    if match:
        try:
            json.loads(match.group())
            return match.group()
        except json.JSONDecodeError:
            pass

    return None


def add_rule(user_id: int, rule_text: str, rule_json: str | None) -> int:
    """Add a new rule to the database."""
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO rules (user_id, rule_text, rule_json) VALUES (?, ?, ?)",
            (user_id, rule_text, rule_json),
        )
        return cursor.lastrowid


def get_rules(user_id: int) -> list[dict]:
    """Get all rules for a user."""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM rules WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def toggle_rule(user_id: int, rule_id: int) -> bool:
    """Toggle a rule active/inactive."""
    with get_db() as db:
        db.execute(
            "UPDATE rules SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ? AND user_id = ?",
            (rule_id, user_id),
        )
    return True


def delete_rule(user_id: int, rule_id: int) -> bool:
    """Delete a rule."""
    with get_db() as db:
        db.execute(
            "DELETE FROM rules WHERE id = ? AND user_id = ?",
            (rule_id, user_id),
        )
    return True
