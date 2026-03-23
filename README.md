# Herald

A free, self-hosted AI email assistant. Herald connects to Gmail, screens your inbox, drafts replies in your voice, and delivers daily digests - all powered by Claude Haiku.

## Features

- **Daily Digest** - Catch up on your entire inbox in 30 seconds
- **Smart Drafts** - AI-drafted replies that sound like you, based on your writing history
- **Ask AI** - Chat with your inbox in plain English ("what emails need my attention?")
- **Plain-Language Rules** - "Always mark emails from @company.com as important"
- **Auto-Archive** - Newsletters and marketing stay out of your inbox
- **One-Click Unsubscribe** - Unsubscribe from mailing lists without leaving Herald
- **Mobile-First PWA** - Works great on your phone, add to home screen

## Quick Start (Local)

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/herald-email-assistant
cd herald-email-assistant
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Gmail API** under APIs and Services
4. Go to **Credentials** and create an **OAuth 2.0 Client ID**
   - Application type: Web application
   - Authorized redirect URIs: `http://localhost:8000/auth/callback`
5. Copy your Client ID and Client Secret

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:
```
ANTHROPIC_API_KEY=your_key_here
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
SECRET_KEY=run-python-c-import-secrets-print-secrets-token-hex-32
```

### 4. Run

```bash
cd src
python app.py
```

Open `http://localhost:8000` in your browser and sign in with Google.

## Deploy to Railway (Free)

Railway gives you 500 free hours/month - plenty for personal use.

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create herald-email-assistant --public --push
```

### 2. Deploy on Railway

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **New Project** > **Deploy from GitHub repo**
3. Select your `herald-email-assistant` repo
4. Railway auto-detects the `railway.toml` and deploys

### 3. Set environment variables on Railway

In your Railway project, go to **Variables** and add:
```
ANTHROPIC_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SECRET_KEY=...
GOOGLE_REDIRECT_URI=https://YOUR-APP.railway.app/auth/callback
```

### 4. Update Google OAuth

Add your Railway URL to the authorized redirect URIs in Google Cloud Console:
```
https://YOUR-APP.railway.app/auth/callback
```

## Deploy to Render (Alternative)

1. Connect your GitHub repo at [render.com](https://render.com)
2. Create a **Web Service** with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn src.app:app --host 0.0.0.0 --port $PORT`
3. Add the same environment variables as above

## Tech Stack

- **Python 3.12** + **FastAPI** - Backend
- **Claude Haiku** (claude-haiku-4-5) - AI classification, drafting, chat
- **Gmail API** - Email access via OAuth2
- **SQLite** - Local storage for emails, drafts, rules
- **Jinja2** + **HTMX** - Server-rendered mobile-first UI
- **TailwindCSS** - Styling via CDN

## Privacy and Safety

- Herald never sends emails without your confirmation
- Herald never deletes emails
- Email content is processed in-memory and never logged
- OAuth tokens are stored locally in SQLite only
- All AI calls go to Anthropic's API (Claude Haiku)

## Architecture

```
herald/
  src/
    app.py              # FastAPI routes
    config.py           # Environment config
    database.py         # SQLite setup
    auth/
      google_oauth.py   # OAuth2 flow
    email/
      gmail_client.py   # Gmail REST API wrapper
      processor.py      # Sync and classify emails
      briefing.py       # Daily digest generator
      drafter.py        # AI reply drafter
      archiver.py       # Auto-archive engine
      unsubscribe.py    # One-click unsubscribe
    ai/
      classifier.py     # Haiku email classifier
      voice_learner.py  # Learn writing style
      chat.py           # AI inbox chat
    rules/
      engine.py         # Plain-language rule engine
    web/
      templates/        # Jinja2 HTML templates
      static/           # CSS, JS, PWA assets
```
