import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import secrets
from datetime import date
from fastapi import FastAPI, Request, Response, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import config
from database import init_db, get_db
from auth.google_oauth import (
    get_auth_url,
    exchange_code_for_tokens,
    get_user_info,
    calculate_token_expiry,
    refresh_access_token,
    is_token_expired,
)
from mail.processor import sync_and_process_emails, get_inbox_summary
from mail.briefing import generate_briefing, get_recent_briefings, get_briefing_by_id
from mail.drafter import draft_reply, push_draft_to_gmail, get_pending_drafts, delete_draft
from mail.archiver import auto_archive_emails
from mail.unsubscribe import perform_unsubscribe, get_gmail_url
from rules.engine import parse_rule_to_json, add_rule, get_rules, toggle_rule, delete_rule
from ai.voice_learner import learn_style_from_sent, get_style_summary, get_sample_count
from ai.chat import chat_with_emails, get_chat_history, save_chat_message, clear_chat_history


app = FastAPI(title="Herald", docs_url=None, redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.APP_SECRET_KEY,
    session_cookie="herald_session",
    max_age=60 * 60 * 24 * 30,  # 30 days
    https_only=False,
)

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "web/static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web/templates"))


@app.on_event("startup")
async def startup():
    init_db()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(user) if user else None


async def get_valid_token(user: dict) -> str:
    """Return a valid access token, refreshing if needed."""
    if is_token_expired(user.get("token_expiry", "")):
        tokens = await refresh_access_token(user["refresh_token"])
        expiry = calculate_token_expiry(tokens.get("expires_in", 3600))
        with get_db() as db:
            db.execute(
                "UPDATE users SET access_token = ?, token_expiry = ? WHERE id = ?",
                (tokens["access_token"], expiry, user["id"]),
            )
        return tokens["access_token"]
    return user["access_token"]


def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/onboarding"})
    return user


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    from datetime import datetime
    summary = get_inbox_summary(user["id"])
    briefings = get_recent_briefings(user["id"], limit=5)
    today = date.today().isoformat()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "summary": summary,
            "briefings": briefings,
            "today": today,
            "now_hour": datetime.now().hour,
            "has_briefing_today": any(b["date"] == today for b in briefings),
        },
    )


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/")
    return templates.TemplateResponse("onboarding.html", {"request": request})


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/auth/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    return RedirectResponse(get_auth_url(state))


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"/onboarding?error={error}")

    stored_state = request.session.get("oauth_state", "")
    if state and stored_state and state != stored_state:
        return RedirectResponse("/onboarding?error=state_mismatch")

    tokens = await exchange_code_for_tokens(code)
    user_info = await get_user_info(tokens["access_token"])

    expiry = calculate_token_expiry(tokens.get("expires_in", 3600))

    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?", (user_info["email"],)
        ).fetchone()

        if existing:
            db.execute(
                """UPDATE users SET name = ?, picture = ?, access_token = ?,
                   refresh_token = COALESCE(?, refresh_token),
                   token_expiry = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE email = ?""",
                (
                    user_info.get("name", ""),
                    user_info.get("picture", ""),
                    tokens["access_token"],
                    tokens.get("refresh_token"),
                    expiry,
                    user_info["email"],
                ),
            )
            user_id = existing["id"]
        else:
            cursor = db.execute(
                """INSERT INTO users (email, name, picture, access_token, refresh_token, token_expiry)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user_info["email"],
                    user_info.get("name", ""),
                    user_info.get("picture", ""),
                    tokens["access_token"],
                    tokens.get("refresh_token", ""),
                    expiry,
                ),
            )
            user_id = cursor.lastrowid

    request.session["user_id"] = user_id
    return RedirectResponse("/?welcome=1")


@app.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/onboarding")


# ---------------------------------------------------------------------------
# Briefing routes
# ---------------------------------------------------------------------------

@app.get("/briefing", response_class=HTMLResponse)
async def briefing_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    briefings = get_recent_briefings(user["id"])
    latest = briefings[0] if briefings else None
    full_briefing = None
    if latest:
        full_briefing = get_briefing_by_id(user["id"], latest["id"])

    return templates.TemplateResponse(
        "briefing.html",
        {
            "request": request,
            "user": user,
            "briefing": full_briefing,
            "briefings": briefings,
        },
    )


@app.get("/briefing/{briefing_id}", response_class=HTMLResponse)
async def briefing_detail(request: Request, briefing_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    briefing = get_briefing_by_id(user["id"], briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    briefings = get_recent_briefings(user["id"])
    return templates.TemplateResponse(
        "briefing.html",
        {
            "request": request,
            "user": user,
            "briefing": briefing,
            "briefings": briefings,
        },
    )


@app.post("/briefing/generate")
async def generate_briefing_route(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    try:
        access_token = await get_valid_token(user)
        await sync_and_process_emails(user["id"], access_token)
        briefing = await generate_briefing(user["id"])
        return RedirectResponse(f"/briefing/{briefing['id']}", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/briefing?error={str(e)[:100]}", status_code=303)


# ---------------------------------------------------------------------------
# Drafts routes
# ---------------------------------------------------------------------------

@app.get("/drafts", response_class=HTMLResponse)
async def drafts_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    drafts = get_pending_drafts(user["id"])
    return templates.TemplateResponse(
        "drafts.html",
        {"request": request, "user": user, "drafts": drafts},
    )


@app.post("/drafts/generate/{email_id}")
async def generate_draft(request: Request, email_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    access_token = await get_valid_token(user)
    await draft_reply(user["id"], email_id, access_token)
    return RedirectResponse("/drafts", status_code=303)


@app.post("/drafts/{draft_id}/push")
async def push_draft(request: Request, draft_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    access_token = await get_valid_token(user)
    await push_draft_to_gmail(user["id"], draft_id, access_token)
    return RedirectResponse("/drafts?pushed=1", status_code=303)


@app.post("/drafts/{draft_id}/delete")
async def remove_draft(request: Request, draft_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    delete_draft(user["id"], draft_id)
    return RedirectResponse("/drafts", status_code=303)


# ---------------------------------------------------------------------------
# Rules routes
# ---------------------------------------------------------------------------

@app.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    rules = get_rules(user["id"])
    return templates.TemplateResponse(
        "rules.html",
        {"request": request, "user": user, "rules": rules},
    )


@app.post("/rules/add")
async def add_rule_route(request: Request, rule_text: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    rule_json = await parse_rule_to_json(rule_text)
    add_rule(user["id"], rule_text, rule_json)
    return RedirectResponse("/rules", status_code=303)


@app.post("/rules/{rule_id}/toggle")
async def toggle_rule_route(request: Request, rule_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    toggle_rule(user["id"], rule_id)
    return RedirectResponse("/rules", status_code=303)


@app.post("/rules/{rule_id}/delete")
async def delete_rule_route(request: Request, rule_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    delete_rule(user["id"], rule_id)
    return RedirectResponse("/rules", status_code=303)


# ---------------------------------------------------------------------------
# Settings routes
# ---------------------------------------------------------------------------

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    sample_count = get_sample_count(user["id"])
    style_summary = get_style_summary(user["id"]) if sample_count > 0 else None

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "sample_count": sample_count,
            "style_summary": style_summary,
        },
    )


@app.post("/settings/sync")
async def manual_sync(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    access_token = await get_valid_token(user)
    result = await sync_and_process_emails(user["id"], access_token)
    return RedirectResponse(f"/?synced={result['synced']}", status_code=303)


@app.post("/settings/learn-style")
async def learn_style(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    access_token = await get_valid_token(user)
    count = await learn_style_from_sent(user["id"], access_token)
    return RedirectResponse(f"/settings?learned={count}", status_code=303)


# ---------------------------------------------------------------------------
# Chat routes
# ---------------------------------------------------------------------------

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    history = get_chat_history(user["id"])
    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "user": user, "history": history},
    )


@app.post("/chat/message")
async def send_chat_message(request: Request, message: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    save_chat_message(user["id"], "user", message)

    result = await chat_with_emails(user["id"], message)
    answer = result["response"]
    email_refs = result["emails"]

    save_chat_message(user["id"], "assistant", answer, [e["id"] for e in email_refs])

    # HTMX response: return just the new message bubbles
    return templates.TemplateResponse(
        "partials/chat_messages.html",
        {
            "request": request,
            "user_message": message,
            "assistant_message": answer,
            "email_refs": email_refs,
        },
    )


@app.post("/chat/clear")
async def clear_chat(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    clear_chat_history(user["id"])
    return RedirectResponse("/chat", status_code=303)


# ---------------------------------------------------------------------------
# Unsubscribe routes
# ---------------------------------------------------------------------------

@app.post("/unsubscribe/{email_id}")
async def unsubscribe_route(request: Request, email_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    access_token = await get_valid_token(user)
    result = await perform_unsubscribe(user["id"], email_id, access_token)

    if result.get("method") == "mailto":
        # Can't auto-trigger mailto, redirect to mailto URL
        return RedirectResponse(result["url"], status_code=303)

    # Return HTMX partial with result
    return templates.TemplateResponse(
        "partials/unsubscribe_result.html",
        {"request": request, "result": result, "email_id": email_id},
    )


# ---------------------------------------------------------------------------
# Email view routes
# ---------------------------------------------------------------------------

@app.get("/email/{email_id}", response_class=HTMLResponse)
async def view_email(request: Request, email_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    with get_db() as db:
        email_row = db.execute(
            "SELECT * FROM emails WHERE id = ? AND user_id = ?",
            (email_id, user["id"]),
        ).fetchone()

    if not email_row:
        raise HTTPException(status_code=404, detail="Email not found")

    email_data = dict(email_row)
    gmail_url = get_gmail_url(email_data["gmail_id"])

    return templates.TemplateResponse(
        "email_view.html",
        {
            "request": request,
            "user": user,
            "email": email_data,
            "gmail_url": gmail_url,
        },
    )


# ---------------------------------------------------------------------------
# Archive routes
# ---------------------------------------------------------------------------

@app.post("/settings/auto-archive")
async def run_auto_archive(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    access_token = await get_valid_token(user)
    result = await auto_archive_emails(user["id"], access_token)
    return RedirectResponse(
        f"/settings?archived={result['archived']}", status_code=303
    )


@app.post("/settings/auto-archive-toggle")
async def toggle_auto_archive(request: Request, enabled: str = Form("on")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/onboarding")

    value = 1 if enabled == "on" else 0
    with get_db() as db:
        db.execute(
            "UPDATE users SET auto_archive_enabled = ? WHERE id = ?",
            (value, user["id"]),
        )
    return RedirectResponse("/settings", status_code=303)


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------

@app.get("/partials/inbox-summary", response_class=HTMLResponse)
async def inbox_summary_partial(request: Request):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("")

    summary = get_inbox_summary(user["id"])
    return templates.TemplateResponse(
        "partials/inbox_summary.html",
        {"request": request, "summary": summary},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
    )
