import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# App
APP_NAME = "Herald"
APP_SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/herald.db")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "herald.db"))

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback"
)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

# Email processing
MAX_EMAILS_TO_PROCESS = int(os.getenv("MAX_EMAILS_TO_PROCESS", "100"))
BRIEFING_HOUR = int(os.getenv("BRIEFING_HOUR", "8"))  # 8 AM

# Port
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
