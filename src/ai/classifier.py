import json
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

IMPORTANCE_LEVELS = ["high", "medium", "low"]
CATEGORIES = [
    "personal",
    "work",
    "finance",
    "newsletter",
    "notification",
    "marketing",
    "social",
    "travel",
    "receipt",
    "general",
]

# Heuristic fast-path to avoid API calls for obvious cases
MARKETING_KEYWORDS = [
    "unsubscribe", "click here", "limited time", "special offer",
    "% off", "sale ends", "shop now", "free shipping", "promo code",
    "newsletter", "marketing", "no-reply", "noreply",
]


class EmailClassifier:
    """Classify emails by importance and category using Claude Haiku."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

    async def classify(self, email: dict) -> tuple[str, str]:
        """Return (importance, category) for an email."""
        # Fast-path heuristics
        fast = self._fast_classify(email)
        if fast:
            return fast

        if not self.client:
            return ("medium", "general")

        try:
            return await self._ai_classify(email)
        except Exception:
            return ("medium", "general")

    def _fast_classify(self, email: dict) -> tuple[str, str] | None:
        """Quick rule-based classification to save API calls."""
        text = (
            (email.get("subject") or "") + " " +
            (email.get("snippet") or "") + " " +
            (email.get("from_address") or "")
        ).lower()

        for kw in MARKETING_KEYWORDS:
            if kw in text:
                return ("low", "marketing")

        label_ids = email.get("label_ids", [])
        if "CATEGORY_PROMOTIONS" in label_ids:
            return ("low", "marketing")
        if "CATEGORY_SOCIAL" in label_ids:
            return ("low", "social")
        if "CATEGORY_UPDATES" in label_ids:
            return ("low", "notification")

        return None

    async def _ai_classify(self, email: dict) -> tuple[str, str]:
        """Use Claude to classify the email."""
        prompt = f"""Classify this email. Reply with JSON only.

From: {email.get('from_name', '')} <{email.get('from_address', '')}>
Subject: {email.get('subject', '')}
Preview: {email.get('snippet', '')[:200]}

Reply with exactly: {{"importance": "high|medium|low", "category": "personal|work|finance|newsletter|notification|marketing|social|travel|receipt|general"}}

Rules:
- high: requires action, from real person, time-sensitive, financial alert
- medium: informational, from known contact, not urgent
- low: newsletter, marketing, automated notification, receipt"""

        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text.strip()
        # Extract JSON even if there's surrounding text
        import re
        match = re.search(r'\{[^}]+\}', text)
        if match:
            data = json.loads(match.group())
            importance = data.get("importance", "medium")
            category = data.get("category", "general")
            if importance not in IMPORTANCE_LEVELS:
                importance = "medium"
            if category not in CATEGORIES:
                category = "general"
            return (importance, category)

        return ("medium", "general")
