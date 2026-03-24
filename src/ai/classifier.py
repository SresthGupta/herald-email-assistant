import json
import re
import subprocess

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

# Heuristic fast-path to avoid CLI calls for obvious cases
MARKETING_KEYWORDS = [
    "unsubscribe", "click here", "limited time", "special offer",
    "% off", "sale ends", "shop now", "free shipping", "promo code",
    "newsletter", "marketing", "no-reply", "noreply",
]


def run_claude(prompt: str) -> str:
    """Run a prompt through the claude CLI and return the output."""
    result = subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip()


class EmailClassifier:
    """Classify emails by importance and category using Claude via CLI."""

    async def classify(self, email: dict) -> tuple[str, str]:
        """Return (importance, category) for an email."""
        # Fast-path heuristics
        fast = self._fast_classify(email)
        if fast:
            return fast

        try:
            return await self._ai_classify(email)
        except Exception:
            return ("medium", "general")

    def _fast_classify(self, email: dict) -> tuple[str, str] | None:
        """Quick rule-based classification to save CLI calls."""
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
        """Use Claude CLI to classify the email."""
        prompt = f"""Classify this email. Reply with JSON only.

From: {email.get('from_name', '')} <{email.get('from_address', '')}>
Subject: {email.get('subject', '')}
Preview: {email.get('snippet', '')[:200]}

Reply with exactly: {{"importance": "high|medium|low", "category": "personal|work|finance|newsletter|notification|marketing|social|travel|receipt|general"}}

Rules:
- high: requires action, from real person, time-sensitive, financial alert
- medium: informational, from known contact, not urgent
- low: newsletter, marketing, automated notification, receipt"""

        text = run_claude(prompt)
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
