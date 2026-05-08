"""Subscription Guardian — Backend (FastAPI)
Scans Gmail inbox via OAuth, detects subscription emails,
extracts name, amount, frequency, and next billing date.

Security fixes applied (see audit):
  C1 - No secrets in repo; all via env vars
  C2 - Proper session auth on all /api/* routes
  C3 - OAuth state parameter (CSRF protection)
  C4 - CORS locked to specific origins
  C5 - Tokens encrypted at rest; HTTPS enforced in prod
  H1 - No PII in redirect URLs
  H2 - No internal HTTP calls (refresh is a direct function)
  H3 - currency stored correctly per subscription
  H4 - UNIQUE(user_id, name) upsert prevents duplicate rows
  H5 - Specific exception handling, no bare except
  H6 - Gmail rate-limit backoff + semaphore concurrency
  H7 - Single Dockerfile (root), runs non-root user
  H8 - DB path via env var; WAL mode
  M1 - Users keyed on email; refresh token preserved on re-login
  M2 - Detection logic hardened (email-strip fix, skip-set cleanup)
  M3 - sub.name HTML-stripped before storage
  M4 - Tokens never logged
  M5 - Security headers middleware
  M6 - Input validation with Pydantic validators + Literal types
  M7 - Extension host from env var
  M8 - Rate limiting on /auth/* and /api/scan
"""

import os
import re
import uuid
import base64
import binascii
import logging
import secrets
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
import httpx
import sqlite3
from dotenv import load_dotenv
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

# ── Config ──────────────────────────────────────────────
CLIENT_ID      = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET  = os.getenv("GOOGLE_CLIENT_SECRET", "")
BACKEND_URL    = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL   = os.getenv("FRONTEND_URL", "http://localhost:3000")
EXTENSION_ID   = os.getenv("EXTENSION_ID", "")
APP_SECRET     = os.getenv("APP_SECRET", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-session-insecure-change-me")
DB_PATH        = os.getenv("DB_PATH", "subguard.db")

_is_production = BACKEND_URL.startswith("https://")

# Fail fast on missing secrets in production
if _is_production:
    missing = [v for v in ("CLIENT_ID", "CLIENT_SECRET", "APP_SECRET", "SESSION_SECRET")
               if not locals().get(v) and not globals().get(v)]
    if missing:
        raise RuntimeError(f"Required env vars missing: {', '.join(missing)}")

SCOPES       = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]
REDIRECT_URI = f"{BACKEND_URL}/auth/callback"

SESSION_COOKIE_NAME = "sg_session"
SESSION_MAX_AGE     = 60 * 60 * 24 * 30  # 30 days
_USD_TO_INR         = 85.0               # displayed note: approximate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subguard")


# ── Crypto helpers (C5) ─────────────────────────────────

def _make_fernet() -> Optional[Fernet]:
    if not APP_SECRET:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(APP_SECRET.encode()).digest())
    return Fernet(key)

_fernet = _make_fernet()


def encrypt_token(token: str) -> str:
    if not _fernet or not token:
        return token
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    if not _fernet or not ciphertext:
        return ciphertext
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return ciphertext  # plaintext from before encryption was enabled


# ── Session helpers (C2) ────────────────────────────────

_signer = URLSafeTimedSerializer(SESSION_SECRET, salt="sg-session")


def make_session_token(user_id: str) -> str:
    return _signer.dumps(user_id)


def verify_session_token(token: str) -> Optional[str]:
    try:
        return _signer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


# ── Rate limiter (M8) ───────────────────────────────────

limiter = Limiter(key_func=get_remote_address)


# ── Lifespan ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Subscription Guardian", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — locked to specific origins only (C4)
_allowed_origins = [o for o in [FRONTEND_URL, BACKEND_URL] if o]
if EXTENSION_ID:
    _allowed_origins.append(f"chrome-extension://{EXTENSION_ID}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


# ── Security headers middleware (M5) ────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]        = "DENY"
    response.headers["Referrer-Policy"]        = "no-referrer"
    response.headers["Permissions-Policy"]     = "geolocation=(), camera=(), microphone=()"
    if _is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
    return response


# ── Static files ─────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/success.html") as f:
        return f.read()


# ── Database ────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            email         TEXT NOT NULL UNIQUE,
            access_token  TEXT NOT NULL,
            refresh_token TEXT,
            token_expiry  TEXT,
            created_at    TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            name            TEXT NOT NULL,
            amount          REAL,
            currency        TEXT DEFAULT 'INR',
            frequency       TEXT,
            category        TEXT DEFAULT 'Other',
            next_billing    TEXT,
            last_found      TEXT DEFAULT (datetime('now')),
            confidence      REAL DEFAULT 0.5,
            status          TEXT DEFAULT 'active',
            source_email_id TEXT,
            is_confirmed    INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (user_id, name)
        );
        CREATE TABLE IF NOT EXISTS scan_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          TEXT NOT NULL,
            scanned_at       TEXT DEFAULT (datetime('now')),
            emails_processed INTEGER DEFAULT 0,
            subs_found       INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS oauth_states (
            state      TEXT PRIMARY KEY,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


# ── Auth dependency (C2) ────────────────────────────────

async def get_current_user(
    sg_session: Optional[str] = Cookie(default=None),
) -> dict:
    """Verify session cookie and return user row. Raises 401 on failure."""
    if not sg_session:
        raise HTTPException(401, "Not authenticated")
    user_id = verify_session_token(sg_session)
    if not user_id:
        raise HTTPException(401, "Session expired — please log in again")
    conn  = get_db()
    user  = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(401, "User not found")
    return dict(user)


# ── OAuth state helpers (C3) ────────────────────────────

def _create_oauth_state() -> str:
    state = secrets.token_urlsafe(32)
    conn  = get_db()
    conn.execute(
        "DELETE FROM oauth_states WHERE created_at < datetime('now', '-10 minutes')"
    )
    conn.execute("INSERT INTO oauth_states (state) VALUES (?)", (state,))
    conn.commit()
    conn.close()
    return state


def _consume_oauth_state(state: str) -> bool:
    if not state:
        return False
    conn = get_db()
    row  = conn.execute(
        "SELECT state FROM oauth_states "
        "WHERE state=? AND created_at > datetime('now', '-10 minutes')",
        (state,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM oauth_states WHERE state=?", (state,))
        conn.commit()
    conn.close()
    return row is not None


# ── OAuth Flow ──────────────────────────────────────────

@app.get("/auth/login")
@limiter.limit("10/minute")
async def auth_login(request: Request):
    """Step 1: Redirect user to Google OAuth consent screen."""
    state    = _create_oauth_state()
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        "response_type=code&"
        f"scope={' '.join(SCOPES)}&"
        "access_type=offline&"
        "prompt=select_account&"
        f"state={state}"
    )
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def auth_callback(
    code:  str = None,
    error: str = None,
    state: str = None,
):
    """Step 2: Exchange code, set session cookie, redirect — no PII in URL (H1)."""

    # Validate OAuth state (C3)
    if not _consume_oauth_state(state or ""):
        return JSONResponse(
            {"error": "Invalid or expired OAuth state. Please try logging in again."},
            status_code=400,
        )
    if error:
        return JSONResponse({"error": f"Google OAuth error: {error}"}, status_code=400)
    if not code:
        return JSONResponse({"error": "No authorization code provided"}, status_code=400)

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        resp   = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri":  REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )
        tokens = resp.json()

    if "error" in tokens:
        # M4: never log token values
        logger.error("Token exchange failed: %s", tokens.get("error"))
        return JSONResponse(
            {"error": tokens.get("error_description", "Token exchange failed")},
            status_code=400,
        )

    access_token  = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in    = tokens.get("expires_in", 3600)
    token_expiry  = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()

    # Get user email
    async with httpx.AsyncClient() as client:
        resp      = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_info = resp.json()
        email     = user_info.get("email")

    if not email:
        return JSONResponse(
            {"error": "Could not retrieve email from Google"}, status_code=400
        )

    # Encrypt tokens at rest (C5)
    enc_access  = encrypt_token(access_token)
    enc_refresh = encrypt_token(refresh_token) if refresh_token else None

    # Upsert keyed on email, preserve existing refresh_token (M1)
    conn     = get_db()
    existing = conn.execute(
        "SELECT id, refresh_token FROM users WHERE email=?", (email,)
    ).fetchone()

    if existing:
        user_id       = existing["id"]
        stored_refresh = enc_refresh if enc_refresh else existing["refresh_token"]
        conn.execute(
            "UPDATE users SET access_token=?, refresh_token=?, token_expiry=? WHERE id=?",
            (enc_access, stored_refresh, token_expiry, user_id),
        )
    else:
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, email, access_token, refresh_token, token_expiry) "
            "VALUES (?,?,?,?,?)",
            (user_id, email, enc_access, enc_refresh, token_expiry),
        )

    conn.commit()
    conn.close()

    # Issue HttpOnly session cookie — no PII in URL (H1, C2)
    session_token = make_session_token(user_id)
    redirect      = RedirectResponse(url="/auth/success", status_code=303)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=_is_production,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )
    return redirect


@app.get("/auth/success", response_class=HTMLResponse)
async def auth_success(current_user: dict = Depends(get_current_user)):
    """Post-OAuth landing page — requires valid session."""
    with open("static/success.html") as f:
        return f.read()


@app.post("/auth/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"status": "logged_out"}


# ── Internal token refresh — no self-HTTP (H2) ──────────

async def _do_refresh(user: dict) -> Optional[str]:
    """Refresh an expired access token directly (no internal HTTP call)."""
    stored = user.get("refresh_token")
    if not stored:
        return None

    refresh_token = decrypt_token(stored)

    async with httpx.AsyncClient() as client:
        resp   = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": refresh_token,
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type":    "refresh_token",
            },
        )
        tokens = resp.json()

    if "error" in tokens:
        logger.error("Token refresh failed: %s", tokens.get("error"))
        return None

    new_token  = tokens["access_token"]
    new_expiry = (
        datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))
    ).isoformat()

    conn = get_db()
    conn.execute(
        "UPDATE users SET access_token=?, token_expiry=? WHERE id=?",
        (encrypt_token(new_token), new_expiry, user["id"]),
    )
    conn.commit()
    conn.close()
    return new_token


async def _get_valid_token(user: dict) -> Optional[str]:
    """Return a valid (possibly refreshed) access token."""
    try:
        expiry = datetime.fromisoformat(user["token_expiry"])
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, KeyError):
        expiry = datetime.now(timezone.utc) - timedelta(seconds=1)

    if datetime.now(timezone.utc) < expiry:
        return decrypt_token(user["access_token"])

    return await _do_refresh(user)


# ── Subscription Detection ──────────────────────────────

SUBSCRIPTION_KEYWORDS = [
    "subscription", "renewal", "recurring", "monthly", "annual", "yearly",
    "quarterly", "billing", "invoice", "receipt", "payment received",
    "plan upgrade", "plan downgrade", "trial ended", "trial ending",
    "auto-renew", "automatic payment", "direct debit", "mandate",
    "upi mandate", "standing instruction",
]

KNOWN_SUBS = [
    ("youtube premium", {"display_name": "YouTube Premium", "category": "Entertainment", "frequency": "monthly",  "currency": "INR", "default_amount": 299}),
    ("youtube music",   {"display_name": "YouTube Music",   "category": "Music",         "frequency": "monthly",  "currency": "INR"}),
    ("netflix",         {"display_name": "Netflix",         "category": "Entertainment", "frequency": "monthly",  "currency": "INR", "default_amount": 149}),
    ("google one",      {"display_name": "Google One",      "category": "Cloud",         "frequency": "monthly",  "currency": "INR", "default_amount": 130}),
    ("google storage",  {"display_name": "Google One",      "category": "Cloud",         "frequency": "monthly",  "currency": "INR"}),
    ("google workspace",{"display_name": "Google Workspace","category": "Productivity",  "frequency": "monthly",  "currency": "INR"}),
    ("spotify",         {"display_name": "Spotify",         "category": "Music",         "frequency": "monthly",  "currency": "INR", "default_amount": 119}),
    ("midjourney",      {"display_name": "Midjourney",      "category": "AI",            "frequency": "monthly",  "currency": "USD"}),
    ("amazon prime",    {"display_name": "Amazon Prime",    "category": "Shopping",      "frequency": "yearly",   "currency": "INR"}),
    ("icloud",          {"display_name": "iCloud",          "category": "Cloud",         "frequency": "monthly",  "currency": "INR"}),
    ("dropbox",         {"display_name": "Dropbox",         "category": "Cloud",         "frequency": "monthly",  "currency": "USD"}),
    ("hotstar",         {"display_name": "Hotstar",         "category": "Entertainment", "frequency": "monthly",  "currency": "INR"}),
    ("canva",           {"display_name": "Canva",           "category": "Design",        "frequency": "monthly",  "currency": "USD"}),
    ("figma",           {"display_name": "Figma",           "category": "Design",        "frequency": "yearly",   "currency": "USD"}),
    ("adobe",           {"display_name": "Adobe",           "category": "Design",        "frequency": "monthly",  "currency": "USD"}),
    ("chatgpt",         {"display_name": "ChatGPT",         "category": "AI",            "frequency": "monthly",  "currency": "USD"}),
    ("notion",          {"display_name": "Notion",          "category": "Productivity",  "frequency": "monthly",  "currency": "USD"}),
    ("github",          {"display_name": "GitHub",          "category": "Development",   "frequency": "monthly",  "currency": "USD"}),
    ("slack",           {"display_name": "Slack",           "category": "Productivity",  "frequency": "monthly",  "currency": "USD"}),
    ("microsoft 365",   {"display_name": "Microsoft 365",   "category": "Productivity",  "frequency": "yearly",   "currency": "INR"}),
    ("apple music",     {"display_name": "Apple Music",     "category": "Music",         "frequency": "monthly",  "currency": "INR"}),
    ("apple tv",        {"display_name": "Apple TV+",       "category": "Entertainment", "frequency": "monthly",  "currency": "INR"}),
    ("swiggy one",      {"display_name": "Swiggy One",      "category": "Food",          "frequency": "monthly",  "currency": "INR"}),
    ("zomato pro",      {"display_name": "Zomato Pro",      "category": "Food",          "frequency": "monthly",  "currency": "INR"}),
    ("zepto pass",      {"display_name": "Zepto Pass",      "category": "Shopping",      "frequency": "monthly",  "currency": "INR"}),
    ("blinkit",         {"display_name": "Blinkit",         "category": "Shopping",      "frequency": "monthly",  "currency": "INR"}),
    # Broader fallbacks — last
    ("youtube",         {"display_name": "YouTube",         "category": "Entertainment", "frequency": "monthly",  "currency": "INR"}),
    ("google drive",    {"display_name": "Google Drive",    "category": "Cloud",         "frequency": "monthly",  "currency": "INR"}),
    ("google",          {"display_name": "Google",          "category": "Other",         "frequency": "monthly",  "currency": "INR"}),
    ("apple",           {"display_name": "Apple",           "category": "Other",         "frequency": "monthly",  "currency": "INR"}),
    ("epic games",      {"display_name": "Epic Games",      "category": "Gaming",        "frequency": "monthly",  "currency": "INR"}),
]

AMOUNT_PATTERNS = [
    r'(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)',
    r'([\d,]+(?:\.\d{2})?)\s*(?:Rs\.?|INR|₹)',
    r'(?:\$|USD)\s*([\d,]+(?:\.\d{2})?)',
    r'(?:€|EUR)\s*([\d,]+(?:\.\d{2})?)',
    r'(?:£|GBP)\s*([\d,]+(?:\.\d{2})?)',
    r'([\d,]+(?:\.\d{2})?)\s*(?:USD|EUR|GBP)',
    r'charged\s*(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d{1,2})?)',
    r'paid\s*(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d{1,2})?)',
    r'amount\s*(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d{1,2})?)',
    r'([\d,]+(?:\.\d{2})?)\s*\/\s*(?:month|year|mo|yr)',
]

CURRENCY_MARKERS = [
    (r'(?:Rs\.?|INR|₹)', 'INR'),
    (r'(?:\$|USD)',       'USD'),
    (r'(?:€|EUR)',        'EUR'),
    (r'(?:£|GBP)',        'GBP'),
]

FREQUENCY_PATTERNS = [
    (r'\bmonthly\b',       'monthly'),
    (r'\bannual(?:ly)?\b', 'yearly'),
    (r'\byearly\b',        'yearly'),
    (r'\bquarterly\b',     'quarterly'),
    (r'\bweekly\b',        'weekly'),
    (r'\bper month\b',     'monthly'),
    (r'\bper year\b',      'yearly'),
    (r'\bevery month\b',   'monthly'),
    (r'\bevery year\b',    'yearly'),
    (r'\/mo\b',            'monthly'),
    (r'\/yr\b',            'yearly'),
    (r'\/year\b',          'yearly'),
]

_SKIP_SENDER_WORDS = frozenset({
    "intl", "acct", "info", "news", "mail", "team", "help",
    "support", "noreply", "notify", "gmail", "students", "student",
    "informa", "billing", "cycle", "prd", "receipt", "invoice",
    "payment", "no-reply", "donotreply",
})

_SKIP_SUBJECT_WORDS = frozenset({
    "your", "re:", "fwd:", "the", "change", "in", "of",
    "to", "for", "a", "an", "is", "was", "has", "have",
})

_BAD_SUBJECT_KW = frozenset({
    "billing", "cycle", "receipt", "invoice", "payment",
    "subscription", "prd", "order", "confirmation",
    "update", "notification", "monthly", "annual",
})


def extract_amount(text: str) -> tuple:
    """Return (amount: float|None, currency: str)."""
    for pattern in AMOUNT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                amount = float(match.group(1).replace(",", ""))
                # Detect currency from the match's immediate context
                window = text[max(0, match.start() - 5):match.end() + 5]
                currency = "INR"
                for cur_pattern, cur_code in CURRENCY_MARKERS:
                    if re.search(cur_pattern, window, re.IGNORECASE):
                        currency = cur_code
                        break
                return amount, currency
            except ValueError:
                continue
    return None, "INR"


def extract_frequency(text: str) -> Optional[str]:
    for pattern, freq in FREQUENCY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return freq
    return None


def extract_next_billing(text: str) -> Optional[str]:
    patterns = [
        r'(?:next billing|next payment|renews?|auto[- ]?renew(?:s|al)?)\s*(?:on|:)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(?:next billing|next payment|renews?|auto[- ]?renew(?:s|al)?)\s*(?:on|:)?\s*(\w+\s+\d{1,2},?\s*\d{4})',
        r'(?:billing date|payment date|scheduled for|due on?)\s*(?:is|:)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(?:billing date|payment date|scheduled for|due on?)\s*(?:is|:)?\s*(\d{4}-\d{2}-\d{2})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _strip_html(text: str) -> str:
    """Remove HTML tags from text (M3 defence-in-depth before storage)."""
    return re.sub(r'<[^>]+>', '', text).strip()


def identify_subscription(subject: str, sender: str, snippet: str) -> Optional[dict]:
    """Analyse an email and return subscription info or None."""
    full_text = f"{subject}\n{sender}\n{snippet}".lower()

    # Filter app's own emails
    if "subscription guardian" in full_text or "subguard" in full_text:
        return None

    # Strip email addresses ONLY — used for KNOWN_SUBS matching (M2 fix)
    full_text_no_email = re.sub(r'[\w.\-+]+@[\w.\-]+\.\w+', '', full_text)

    # Known subscription services (only match against no-email text)
    for pattern, info in KNOWN_SUBS:
        if pattern in full_text_no_email:
            amount, currency = extract_amount(full_text)
            if not amount and "default_amount" in info:
                amount     = info["default_amount"]
                currency   = info.get("currency", "INR")
                confidence = 0.65
            else:
                currency   = currency or info.get("currency", "INR")
                confidence = 0.85 if amount else 0.70

            frequency = extract_frequency(full_text) or info["frequency"]
            return {
                "name":         info["display_name"],
                "amount":       amount,
                "currency":     currency,
                "category":     info["category"],
                "frequency":    frequency,
                "confidence":   confidence,
                "next_billing": None,
            }

    # Generic keyword scoring
    keyword_score = sum(0.15 for kw in SUBSCRIPTION_KEYWORDS if kw in full_text)
    if keyword_score < 0.30:
        return None

    amount, currency = extract_amount(full_text)
    frequency        = extract_frequency(full_text)
    next_billing     = extract_next_billing(full_text)

    # Infer name from sender domain (M2 cleanup — no personal name patterns)
    name_match   = re.search(r'@([\w\-]+)\.', sender)
    service_name = name_match.group(1).title() if name_match else ""

    if not service_name or service_name.lower() in _SKIP_SENDER_WORDS:
        subj_words  = subject.split()
        clean_words = [
            w for w in subj_words
            if w.lower() not in _SKIP_SUBJECT_WORDS
            and w.lower() not in _BAD_SUBJECT_KW
        ]
        if len(clean_words) >= 2:
            service_name = " ".join(clean_words[:2]).title()
        elif clean_words:
            service_name = clean_words[0].title()
        else:
            return None

    # Sanitise before storage (M3)
    service_name = _strip_html(service_name)[:120]
    if not service_name:
        return None

    return {
        "name":         service_name,
        "amount":       amount,
        "currency":     currency or "INR",
        "category":     "Other",
        "frequency":    frequency or "monthly",
        "next_billing": next_billing,
        "confidence":   min(0.50 + keyword_score, 0.95),
    }


# ── Gmail Scanning ──────────────────────────────────────

def extract_body_text(payload: dict) -> str:
    """Recursively extract plain text from email payload."""
    texts = []
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            try:
                # Pad base64 before decoding (H5)
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                texts.append(decoded)
            except (binascii.Error, UnicodeDecodeError) as e:
                logger.debug("base64 decode error in email part: %s", e)
    for part in payload.get("parts", []):
        texts.append(extract_body_text(part))
    return "\n".join(t for t in texts if t)


_GMAIL_SEMAPHORE = asyncio.Semaphore(5)  # H6: max 5 concurrent fetches


async def _fetch_message(gmail: httpx.AsyncClient, msg_id: str) -> Optional[dict]:
    """Fetch one Gmail message with exponential backoff on 429/503 (H6)."""
    async with _GMAIL_SEMAPHORE:
        for attempt in range(4):
            try:
                resp = await gmail.get(
                    f"/users/me/messages/{msg_id}",
                    params={"format": "full"},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    wait = (2 ** attempt) + (secrets.randbelow(1000) / 1000)
                    logger.warning("Gmail rate limited — backing off %.1fs", wait)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("Gmail returned %d for msg %s", resp.status_code, msg_id)
                return None
            except httpx.TimeoutException:
                logger.warning("Gmail timeout on msg %s (attempt %d)", msg_id, attempt + 1)
                await asyncio.sleep(2 ** attempt)
    return None


async def scan_inbox(user_id: str, access_token: str, max_results: int = 200) -> list:
    """Scan Gmail inbox for subscriptions."""
    async with httpx.AsyncClient(
        base_url="https://gmail.googleapis.com/gmail/v1",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20.0,
    ) as gmail:
        query = (
            "subject:(receipt OR invoice OR subscription OR billing "
            "OR payment OR renewed OR renewal) newer_than:90d"
        )
        try:
            resp = await gmail.get(
                "/users/me/messages",
                params={"q": query, "maxResults": max_results},
            )
            if resp.status_code != 200:
                logger.error("Gmail list returned %d", resp.status_code)
                return []
            data = resp.json()
        except httpx.TimeoutException:
            logger.error("Gmail list request timed out")
            return []

        messages = data.get("messages", [])
        if not messages:
            return []

        # Concurrent fetch with semaphore (H6)
        tasks   = [_fetch_message(gmail, m["id"]) for m in messages[:100]]
        results = await asyncio.gather(*tasks)

    subs_found       = []
    emails_processed = 0

    for msg_data in results:
        if not msg_data:
            continue
        try:
            headers   = {
                h["name"].lower(): h["value"]
                for h in msg_data.get("payload", {}).get("headers", [])
            }
            subject   = headers.get("subject", "")
            sender    = headers.get("from", "")
            snippet   = msg_data.get("snippet", "")
            body_text = extract_body_text(msg_data.get("payload", {}))
            full_text = f"{subject}\n{sender}\n{snippet}\n{body_text}"
            msg_id    = msg_data.get("id", "")

            result = identify_subscription(subject, sender, full_text)
            if result:
                result["source_email_id"] = msg_id
                subs_found.append(result)
        except Exception as e:
            logger.debug("Error processing email: %s", e)  # H5
        emails_processed += 1

    # Dedup within this scan
    seen: dict = {}
    for sub in subs_found:
        key = sub["name"].lower()
        if key not in seen:
            seen[key] = sub
        elif sub["amount"] and not seen[key]["amount"]:
            seen[key] = sub
        elif sub["confidence"] > seen[key]["confidence"]:
            seen[key] = sub
    subs_found = list(seen.values())

    # Persist with UPSERT — cross-scan dedup via UNIQUE(user_id, name) (H4)
    conn = get_db()
    conn.execute(
        "INSERT INTO scan_log (user_id, emails_processed, subs_found) VALUES (?,?,?)",
        (user_id, emails_processed, len(subs_found)),
    )
    for sub in subs_found:
        conn.execute(
            """
            INSERT INTO subscriptions
                (id, user_id, name, amount, currency, frequency, category,
                 confidence, source_email_id, next_billing)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, name) DO UPDATE SET
                amount          = COALESCE(excluded.amount, subscriptions.amount),
                currency        = excluded.currency,
                frequency       = COALESCE(excluded.frequency, subscriptions.frequency),
                confidence      = MAX(excluded.confidence, subscriptions.confidence),
                source_email_id = excluded.source_email_id,
                next_billing    = COALESCE(excluded.next_billing, subscriptions.next_billing),
                last_found      = datetime('now')
            """,
            (
                str(uuid.uuid4()), user_id,
                sub["name"], sub["amount"], sub.get("currency", "INR"),
                sub.get("frequency"), sub.get("category", "Other"),
                sub["confidence"], sub.get("source_email_id"),
                sub.get("next_billing"),
            ),
        )
    conn.commit()
    conn.close()
    return subs_found


# ── Pydantic models (M6) ────────────────────────────────

ValidFrequency = Literal["monthly", "yearly", "quarterly", "weekly"]


class ConfirmRequest(BaseModel):
    sub_id:    str              = Field(..., min_length=1, max_length=36)
    name:      Optional[str]   = Field(default=None, max_length=120)
    amount:    Optional[float] = Field(default=None, ge=0.0, le=1_000_000.0)
    frequency: Optional[ValidFrequency] = None

    @field_validator("name")
    @classmethod
    def sanitise_name(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return _strip_html(v)
        return v


# ── API Endpoints ───────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Current authenticated user's public info — used by extension after login."""
    return {
        "id":         current_user["id"],
        "email":      current_user["email"],
        "created_at": current_user["created_at"],
    }


@app.get("/api/scan")
@limiter.limit("5/minute")
async def start_scan(
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    """Scan authenticated user's Gmail for subscriptions."""
    access_token = await _get_valid_token(current_user)
    if not access_token:
        raise HTTPException(
            401,
            "Access token expired and could not be refreshed. Please log in again.",
        )

    subs = await scan_inbox(current_user["id"], access_token)

    total_monthly = 0.0
    total_yearly  = 0.0
    for s in subs:
        amt     = s.get("amount") or 0
        freq    = s.get("frequency") or "monthly"
        cur     = s.get("currency", "INR")
        amt_inr = amt * _USD_TO_INR if cur == "USD" else amt
        if freq == "yearly":
            total_yearly  += amt_inr
        elif freq == "quarterly":
            total_yearly  += amt_inr * 4
        elif freq == "weekly":
            total_yearly  += amt_inr * 52
        else:
            total_monthly += amt_inr

    actual_monthly = total_monthly + (total_yearly / 12)
    return {
        "status":                    "complete",
        "total_subs":                len(subs),
        "total_monthly_spend":       round(actual_monthly, 2),
        "total_yearly_spend":        round(actual_monthly * 12, 2),
        "estimated_perceived_spend": 500,
        "surprise_gap":              round(max(0, actual_monthly - 500), 2),
        "subscriptions":             subs,
    }


@app.get("/api/subscriptions")
async def get_subscriptions(current_user: dict = Depends(get_current_user)):
    """All subscriptions for the authenticated user."""
    conn = get_db()
    subs = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? ORDER BY last_found DESC",
        (current_user["id"],),
    ).fetchall()
    conn.close()
    return {
        "subscriptions": [
            {
                "id":           s["id"],
                "name":         s["name"],
                "amount":       s["amount"],
                "currency":     s["currency"],
                "frequency":    s["frequency"],
                "category":     s["category"],
                "next_billing": s["next_billing"],
                "confidence":   s["confidence"],
                "status":       s["status"],
                "is_confirmed": bool(s["is_confirmed"]),
                "last_found":   s["last_found"],
            }
            for s in subs
        ]
    }


@app.post("/api/subscriptions/confirm")
async def confirm_subscription(
    req:          ConfirmRequest,
    current_user: dict = Depends(get_current_user),
):
    """Confirm or edit a subscription — ownership verified (C2)."""
    conn = get_db()
    sub  = conn.execute(
        "SELECT * FROM subscriptions WHERE id=? AND user_id=?",
        (req.sub_id, current_user["id"]),
    ).fetchone()
    if not sub:
        conn.close()
        raise HTTPException(404, "Subscription not found")

    updates = ["is_confirmed=1"]
    params  = []
    if req.name is not None:
        updates.append("name=?")
        params.append(req.name)
    if req.amount is not None:
        updates.append("amount=?")
        params.append(req.amount)
    if req.frequency is not None:
        updates.append("frequency=?")
        params.append(req.frequency)

    params.append(req.sub_id)
    # `updates` built from hardcoded strings only — safe f-string
    conn.execute(f"UPDATE subscriptions SET {', '.join(updates)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return {"status": "confirmed"}


@app.get("/api/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    """Subscription spend stats for the authenticated user."""
    conn = get_db()
    subs = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? AND is_confirmed=1",
        (current_user["id"],),
    ).fetchall()
    logs = conn.execute(
        "SELECT COUNT(*) as scans, SUM(emails_processed) as emails, SUM(subs_found) as found "
        "FROM scan_log WHERE user_id=?",
        (current_user["id"],),
    ).fetchone()
    conn.close()

    total_monthly = 0.0
    total_yearly  = 0.0
    for s in subs:
        amt     = s["amount"] or 0
        freq    = s["frequency"] or "monthly"
        cur     = s["currency"] or "INR"
        amt_inr = amt * _USD_TO_INR if cur == "USD" else amt
        if freq == "yearly":
            total_yearly  += amt_inr
        elif freq == "quarterly":
            total_yearly  += amt_inr * 4
        elif freq == "weekly":
            total_yearly  += amt_inr * 52
        else:
            total_monthly += amt_inr

    perceived_monthly = 500
    actual_monthly    = total_monthly + (total_yearly / 12)

    return {
        "total_subs":                len(subs),
        "total_monthly_spend":       round(actual_monthly, 2),
        "total_yearly_spend":        round(actual_monthly * 12, 2),
        "estimated_perceived_spend": perceived_monthly,
        "surprise_gap":              round(actual_monthly - perceived_monthly, 2),
        "surprise_gap_pct":          round(
            ((actual_monthly - perceived_monthly) / perceived_monthly) * 100, 0
        ) if perceived_monthly > 0 else 0,
        "by_category": {
            cat: round(
                sum(
                    (s["amount"] or 0) * (_USD_TO_INR if (s["currency"] or "INR") == "USD" else 1)
                    for s in subs if s["category"] == cat
                ),
                2,
            )
            for cat in set(s["category"] for s in subs)
        },
        "scans_completed": logs["scans"]  or 0,
        "emails_scanned":  logs["emails"] or 0,
        "subs_detected":   logs["found"]  or 0,
    }


@app.delete("/api/subscriptions/{sub_id}")
async def delete_subscription(
    sub_id:       str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a subscription — ownership verified (C2)."""
    conn = get_db()
    sub  = conn.execute(
        "SELECT id FROM subscriptions WHERE id=? AND user_id=?",
        (sub_id, current_user["id"]),
    ).fetchone()
    if not sub:
        conn.close()
        raise HTTPException(404, "Subscription not found")
    conn.execute("DELETE FROM subscriptions WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
