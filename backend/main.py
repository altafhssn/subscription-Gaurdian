"""Subscription Guardian — Backend (FastAPI)
Scans Gmail inbox via OAuth, detects subscription emails,
extracts name, amount, frequency, and next billing date.
"""

import os
import re
import json
import uuid
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./subguard.db")
APP_SECRET = os.getenv("APP_SECRET", "dev-secret-change-me")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-session-secret")

DB_PATH = "subguard.db"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/userinfo.email"]
REDIRECT_URI = f"{BACKEND_URL}/auth/callback"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subguard")

app = FastAPI(title="Subscription Guardian")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "chrome-extension://*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static Files (Frontend) ────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    """Landing page — redirect to login or show results."""
    with open("static/success.html") as f:
        return f.read()


@app.get("/auth/success", response_class=HTMLResponse)
async def auth_success(user_id: str = None, email: str = None):
    """OAuth success page with scan interface."""
    with open("static/success.html") as f:
        html = f.read()
    return html

# ── Database ────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            token_expiry TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL,
            currency TEXT DEFAULT 'INR',
            frequency TEXT,
            category TEXT DEFAULT 'Other',
            next_billing TEXT,
            last_found TEXT DEFAULT (datetime('now')),
            confidence REAL DEFAULT 0.5,
            status TEXT DEFAULT 'active',
            source_email_id TEXT,
            is_confirmed INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            scanned_at TEXT DEFAULT (datetime('now')),
            emails_processed INTEGER DEFAULT 0,
            subs_found INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()

init_db()

# ── OAuth Flow ──────────────────────────────────────────

@app.get("/auth/login")
async def auth_login():
    """Step 1: Redirect user to Google OAuth consent screen."""
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        "response_type=code&"
        f"scope={' '.join(SCOPES)}&"
        "access_type=offline&"
        "prompt=consent"
    )
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def auth_callback(code: str = None, error: str = None, request: Request = None):
    """Step 2: Google redirects here with auth code. Exchange for tokens."""
    if error:
        return JSONResponse({"error": f"Google OAuth error: {error}"}, status_code=400)
    if not code:
        return JSONResponse({"error": "No authorization code provided"}, status_code=400)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        tokens = resp.json()

    if "error" in tokens:
        logger.error(f"Token exchange failed: {tokens}")
        return JSONResponse({"error": tokens.get("error_description", "Token exchange failed")}, status_code=400)

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)
    token_expiry = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

    # Get user email
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_info = resp.json()
        email = user_info.get("email", "unknown@email.com")

    # Store user
    user_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO users (id, email, access_token, refresh_token, token_expiry) VALUES (?, ?, ?, ?, ?)",
        (user_id, email, access_token, refresh_token, token_expiry),
    )
    conn.commit()
    conn.close()

    # Redirect to frontend with user_id
    redirect = f"{BACKEND_URL}/auth/success?user_id={user_id}&email={email}"
    return RedirectResponse(url=redirect)


@app.post("/auth/refresh/{user_id}")
async def refresh_token(user_id: str):
    """Refresh an expired access token."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or not user["refresh_token"]:
        conn.close()
        return JSONResponse({"error": "No refresh token available"}, status_code=400)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": user["refresh_token"],
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )
        tokens = resp.json()

    if "error" in tokens:
        conn.close()
        return JSONResponse({"error": tokens.get("error_description", "Refresh failed")}, status_code=400)

    new_token = tokens["access_token"]
    new_expiry = (datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))).isoformat()

    conn.execute("UPDATE users SET access_token=?, token_expiry=? WHERE id=?", (new_token, new_expiry, user_id))
    conn.commit()
    conn.close()

    return {"status": "ok", "access_token": new_token}


# ── Subscription Detection Engine ──────────────────────

# Keywords that strongly suggest a subscription
SUBSCRIPTION_KEYWORDS = [
    "subscription", "renewal", "recurring", "monthly", "annual", "yearly",
    "quarterly", "billing", "invoice", "receipt", "payment received",
    "plan upgrade", "plan downgrade", "trial ended", "trial ending",
    "auto-renew", "automatic payment", "direct debit", "mandate",
    "upi mandate", "standing instruction",
]

# Known subscription services (name patterns) — first match wins, ordered by specificity
KNOWN_SUBS = [
    ("youtube premium", {"display_name": "YouTube Premium", "category": "Entertainment", "frequency": "monthly", "currency": "INR", "default_amount": 299}),
    ("youtube music", {"display_name": "YouTube Music", "category": "Music", "frequency": "monthly", "currency": "INR"}),
    ("netflix", {"display_name": "Netflix", "category": "Entertainment", "frequency": "monthly", "currency": "INR", "default_amount": 149}),
    ("google one", {"display_name": "Google One", "category": "Cloud", "frequency": "monthly", "currency": "INR", "default_amount": 130}),
    ("google storage", {"display_name": "Google One", "category": "Cloud", "frequency": "monthly", "currency": "INR"}),
    ("google drive", {"display_name": "Google One", "category": "Cloud", "frequency": "monthly", "currency": "INR"}),
    ("google workspace", {"display_name": "Google Workspace", "category": "Productivity", "frequency": "monthly", "currency": "INR"}),
    ("spotify", {"display_name": "Spotify", "category": "Music", "frequency": "monthly", "currency": "INR", "default_amount": 119}),
    ("midjourney", {"display_name": "Midjourney", "category": "AI", "frequency": "monthly", "currency": "USD"}),
    ("amazon prime", {"display_name": "Amazon Prime", "category": "Shopping", "frequency": "yearly", "currency": "INR"}),
    ("icloud", {"display_name": "iCloud", "category": "Cloud", "frequency": "monthly", "currency": "INR"}),
    ("dropbox", {"display_name": "Dropbox", "category": "Cloud", "frequency": "monthly", "currency": "USD"}),
    ("hotstar", {"display_name": "Hotstar", "category": "Entertainment", "frequency": "monthly", "currency": "INR"}),
    ("canva", {"display_name": "Canva", "category": "Design", "frequency": "monthly", "currency": "USD"}),
    ("figma", {"display_name": "Figma", "category": "Design", "frequency": "yearly", "currency": "USD"}),
    ("adobe", {"display_name": "Adobe", "category": "Design", "frequency": "monthly", "currency": "USD"}),
    ("chatgpt", {"display_name": "ChatGPT", "category": "AI", "frequency": "monthly", "currency": "USD"}),
    ("notion", {"display_name": "Notion", "category": "Productivity", "frequency": "monthly", "currency": "USD"}),
    ("github", {"display_name": "GitHub", "category": "Development", "frequency": "monthly", "currency": "USD"}),
    ("slack", {"display_name": "Slack", "category": "Productivity", "frequency": "monthly", "currency": "USD"}),
    ("microsoft 365", {"display_name": "Microsoft 365", "category": "Productivity", "frequency": "yearly", "currency": "INR"}),
    ("apple music", {"display_name": "Apple Music", "category": "Music", "frequency": "monthly", "currency": "INR"}),
    ("apple tv", {"display_name": "Apple TV+", "category": "Entertainment", "frequency": "monthly", "currency": "INR"}),
    ("swiggy one", {"display_name": "Swiggy One", "category": "Food", "frequency": "monthly", "currency": "INR"}),
    ("zomato pro", {"display_name": "Zomato Pro", "category": "Food", "frequency": "monthly", "currency": "INR"}),
    ("zepto pass", {"display_name": "Zepto Pass", "category": "Shopping", "frequency": "monthly", "currency": "INR"}),
    ("blinkit", {"display_name": "Blinkit", "category": "Shopping", "frequency": "monthly", "currency": "INR"}),
    # Broader catches (lower priority)
    ("youtube", {"display_name": "YouTube", "category": "Entertainment", "frequency": "monthly", "currency": "INR"}),
    ("google", {"display_name": "Google", "category": "Other", "frequency": "monthly", "currency": "INR"}),
    ("apple", {"display_name": "Apple", "category": "Other", "frequency": "monthly", "currency": "INR"}),
    ("epic games", {"display_name": "Epic Games", "category": "Gaming", "frequency": "monthly", "currency": "INR"}),
]

# Amount patterns (Indian + global)
AMOUNT_PATTERNS = [
    r'(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)',
    r'([\d,]+(?:\.\d{2})?)\s*(?:Rs\.?|INR|₹)',
    r'(?:\$|USD|€|GBP|£)\s*([\d,]+(?:\.\d{2})?)',
    r'([\d,]+(?:\.\d{2})?)\s*(?:USD|EUR|GBP)',
    r'charged\s*(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d{1,2})?)',
    r'paid\s*(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d{1,2})?)',
    r'amount\s*(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d{1,2})?)',
    r'([\d,]+(?:\.\d{2})?)\s*\/\s*(?:month|year|mo|yr)',
]

FREQUENCY_PATTERNS = [
    (r'\bmonthly\b', 'monthly'),
    (r'\bannual(?:ly)?\b', 'yearly'),
    (r'\byearly\b', 'yearly'),
    (r'\bquarterly\b', 'quarterly'),
    (r'\bweekly\b', 'weekly'),
    (r'\bper month\b', 'monthly'),
    (r'\bper year\b', 'yearly'),
    (r'\bevery month\b', 'monthly'),
    (r'\bevery year\b', 'yearly'),
    (r'\/mo\b', 'monthly'),
    (r'\/yr\b', 'yearly'),
    (r'\/year\b', 'yearly'),
]


def extract_amount(text: str) -> Optional[float]:
    """Extract payment amount from text."""
    for pattern in AMOUNT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                amount_str = match.group(1).replace(",", "")
                return float(amount_str)
            except ValueError:
                continue
    return None


def extract_frequency(text: str) -> Optional[str]:
    """Detect billing frequency from text."""
    for pattern, freq in FREQUENCY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return freq
    return None


def extract_next_billing(text: str) -> Optional[str]:
    """Try to find next billing date."""
    date_patterns = [
        r'(?:next billing|next payment|renews?|auto[- ]?renew(?:s|al)?)\s*(?:on|:)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(?:next billing|next payment|renews?|auto[- ]?renew(?:s|al)?)\s*(?:on|:)?\s*(\w+\s+\d{1,2},?\s*\d{4})',
        r'(?:billing date|payment date)\s*(?:is|:)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            # Normalize date
            return date_str
    return None


def identify_subscription(subject: str, sender: str, snippet: str) -> Optional[dict]:
    """
    Analyze an email to detect if it's about a subscription.
    Returns subscription info or None.
    """
    full_text = f"{subject}\n{sender}\n{snippet}".lower()

    # Filter out the app's own emails
    if "subscription guardian" in full_text.lower() or "subguard" in full_text.lower():
        return None

    # Exclude false positives from email addresses containing service names
    full_text_no_email = re.sub(r'[\w.-]+@[\w.-]+\.\w+', '', full_text)

    # Check for known subscription services first
    for pattern, info in KNOWN_SUBS:
        if pattern in full_text_no_email or pattern in full_text:
            amount = extract_amount(full_text)
            # Fallback to default amount if email doesn't include it
            if not amount and "default_amount" in info:
                amount = info["default_amount"]
            frequency = extract_frequency(full_text) or info["frequency"]
            currency = info.get("currency", "INR")
            # Convert USD to INR for Midjourney and other USD services
            if currency == "USD" and amount:
                amount = round(amount * 83, 2)  # ~83 INR per USD
            confidence = 0.85 if amount else 0.7
            # Boost confidence if we used default amount
            if "default_amount" in info and not extract_amount(full_text):
                confidence = 0.65  # Lower confidence since we guessed the amount
            return {
                "name": info["display_name"],
                "amount": amount,
                "category": info["category"],
                "frequency": frequency,
                "currency": currency,
                "confidence": confidence,
            }

    # Generic subscription keyword detection
    keyword_score = 0
    for kw in SUBSCRIPTION_KEYWORDS:
        if kw in full_text:
            keyword_score += 0.15

    if keyword_score >= 0.3:
        amount = extract_amount(full_text)
        frequency = extract_frequency(full_text)
        next_billing = extract_next_billing(full_text)

        # Try to infer service name from sender
        name_match = re.search(r'@([\w-]+)\.', sender)
        service_name = name_match.group(1).title() if name_match else "Unknown Service"

        # Skip bad generic names (too short or meaningless)
        skip_words = {"intl", "acct", "info", "news", "mail", "team", "help", "support", "noreply", "notify", "gmail", "students", "student", "informa"}
        # Also skip names that look like human names (2 words, capitalised)
        skip_if_subject_fragment = {"altaf", "billing", "cycle", "prd", "receipt", "invoice", "payment"}
        
        if service_name.lower() in skip_words or service_name.lower() in skip_if_subject_fragment:
            # Try to get a better name from the subject
            subj_words = subject.split()
            # Remove common prefixes like "Your", "Re:", "Fwd:"
            clean_words = [w for w in subj_words if w.lower() not in {"your", "re:", "fwd:", "the", "change", "in", "of", "to", "for", "a", "an"}]
            # Filter out subject-only fragments that aren't service names
            bad_subject_kw = {"billing", "cycle", "receipt", "invoice", "payment", "subscription", "prd", "order", "confirmation", "update", "notification"}
            clean_words = [w for w in clean_words if w.lower() not in bad_subject_kw]
            if len(clean_words) >= 2:
                service_name = " ".join(clean_words[:2]).title()
            elif clean_words and clean_words[0].lower() not in skip_words:
                service_name = clean_words[0].title()
            else:
                return None  # Skip this email entirely, not useful

        return {
            "name": service_name,
            "amount": amount,
            "category": "Other",
            "frequency": frequency or "monthly",
            "confidence": min(0.5 + keyword_score, 0.95),
        }

    return None


# ── Gmail Scanning ──────────────────────────────────────

async def get_gmail_service(access_token: str):
    """Create an httpx client authenticated for Gmail API."""
    client = httpx.AsyncClient(
        base_url="https://gmail.googleapis.com/gmail/v1",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return client


def extract_body_text(payload: dict) -> str:
    """Recursively extract text from email payload parts."""
    texts = []

    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        try:
            decoded = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
            texts.append(decoded)
        except:
            pass

    # Handle multipart messages
    for part in payload.get("parts", []):
        texts.append(extract_body_text(part))

    return "\n".join(t for t in texts if t)


async def scan_inbox(user_id: str, access_token: str, max_results: int = 200):
    """
    Scan recent inbox emails for subscription-related messages.
    Returns list of detected subscriptions.
    """
    async with await get_gmail_service(access_token) as gmail:
        # Search for subscription-related emails
        query = "subject:(receipt OR invoice OR subscription OR billing OR payment OR renewed OR renewal) newer_than:90d"
        
        resp = await gmail.get(
            "/users/me/messages",
            params={"q": query, "maxResults": max_results},
        )
        data = resp.json()

        messages = data.get("messages", [])
        if not messages:
            logger.info(f"No subscription emails found for {user_id}")
            return []

        subs_found = []
        emails_processed = 0

        for msg in messages[:100]:  # Process first 100 to stay within rate limits
            msg_id = msg["id"]
            resp = await gmail.get(f"/users/me/messages/{msg_id}", params={"format": "full"})
            msg_data = resp.json()

            headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            subject = headers.get("subject", "")
            sender = headers.get("from", "")
            snippet = msg_data.get("snippet", "")

            # Extract full body text for better amount detection
            body_text = extract_body_text(msg_data.get("payload", {}))
            full_text = f"{subject}\n{sender}\n{snippet}\n{body_text}"

            result = identify_subscription(subject, sender, full_text)
            if result:
                result["source_email_id"] = msg_id
                subs_found.append(result)

            emails_processed += 1

        # Deduplicate: keep best (highest confidence, then highest amount) per name
        seen = {}
        for sub in subs_found:
            name = sub["name"].lower()
            if name not in seen:
                seen[name] = sub
            else:
                # Prefer the one with amount
                if sub["amount"] and not seen[name]["amount"]:
                    seen[name] = sub
                # Or higher confidence
                elif sub["confidence"] > seen[name]["confidence"]:
                    seen[name] = sub
        subs_found = list(seen.values())

        # Log scan
        conn = get_db()
        conn.execute(
            "INSERT INTO scan_log (user_id, emails_processed, subs_found) VALUES (?, ?, ?)",
            (user_id, emails_processed, len(subs_found)),
        )

        # Store found subscriptions
        for sub in subs_found:
            sub_id = str(uuid.uuid4())
            conn.execute(
                """INSERT OR IGNORE INTO subscriptions 
                (id, user_id, name, amount, frequency, category, confidence, source_email_id, next_billing)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sub_id, user_id, sub["name"], sub["amount"],
                    sub.get("frequency"), sub.get("category", "Other"),
                    sub["confidence"], sub["source_email_id"],
                    sub.get("next_billing"),
                ),
            )
        conn.commit()
        conn.close()

        return subs_found


# ── API Endpoints ───────────────────────────────────────

class ScanRequest(BaseModel):
    user_id: str


class ConfirmRequest(BaseModel):
    sub_id: str
    name: Optional[str] = None
    amount: Optional[float] = None
    frequency: Optional[str] = None


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    conn = get_db()
    user = conn.execute("SELECT id, email, created_at FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(404, "User not found")
    return dict(user)


@app.get("/api/scan/{user_id}")
async def start_scan_get(user_id: str):
    """Scan user's inbox — GET variant for frontend."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)

    access_token = user["access_token"]

    # Check if token needs refresh
    if user["token_expiry"]:
        try:
            token_expiry = datetime.fromisoformat(user["token_expiry"])
            if datetime.utcnow() > token_expiry and user["refresh_token"]:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{BACKEND_URL}/auth/refresh/{user_id}",
                    )
                    if resp.status_code == 200:
                        access_token = resp.json().get("access_token", access_token)
        except:
            pass

    subs = await scan_inbox(user_id, access_token)
    
    # Get stats
    conn = get_db()
    total_monthly = 0
    total_yearly = 0
    for s in subs:
        amt = s.get("amount") or 0
        freq = s.get("frequency") or "monthly"
        if freq == "yearly":
            total_yearly += amt
        elif freq == "quarterly":
            total_yearly += amt * 4
        elif freq == "weekly":
            total_yearly += amt * 52
        else:
            total_monthly += amt
    conn.close()

    actual_monthly = total_monthly + (total_yearly / 12)
    perceived = 500
    
    return {
        "status": "complete",
        "total_subs": len(subs),
        "total_monthly_spend": round(actual_monthly, 2),
        "total_yearly_spend": round(actual_monthly * 12, 2),
        "estimated_perceived_spend": perceived,
        "surprise_gap": round(max(0, actual_monthly - perceived), 2),
        "subscriptions": subs,
    }


@app.post("/api/scan")
async def start_scan(req: ScanRequest):
    """Scan user's inbox for subscriptions."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (req.user_id,)).fetchone()
    conn.close()

    if not user:
        raise HTTPException(404, "User not found")

    # Check if token needs refresh
    token_expiry = datetime.fromisoformat(user["token_expiry"])
    access_token = user["access_token"]
    
    if datetime.utcnow() > token_expiry and user["refresh_token"]:
        # Token expired, use refresh endpoint
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BACKEND_URL}/auth/refresh/{req.user_id}",
            )
            if resp.status_code == 200:
                access_token = resp.json().get("access_token", access_token)

    subs = await scan_inbox(req.user_id, access_token)
    return {"status": "complete", "subscriptions_found": len(subs), "subscriptions": subs}


@app.get("/api/subscriptions/{user_id}")
async def get_subscriptions(user_id: str):
    """Get all detected subscriptions for a user."""
    conn = get_db()
    subs = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? ORDER BY last_found DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    
    return {
        "subscriptions": [
            {
                "id": s["id"],
                "name": s["name"],
                "amount": s["amount"],
                "currency": s["currency"],
                "frequency": s["frequency"],
                "category": s["category"],
                "next_billing": s["next_billing"],
                "confidence": s["confidence"],
                "status": s["status"],
                "is_confirmed": bool(s["is_confirmed"]),
                "last_found": s["last_found"],
            }
            for s in subs
        ]
    }


@app.post("/api/subscriptions/confirm")
async def confirm_subscription(req: ConfirmRequest):
    """User confirms or edits a detected subscription."""
    conn = get_db()
    sub = conn.execute("SELECT * FROM subscriptions WHERE id=?", (req.sub_id,)).fetchone()
    if not sub:
        conn.close()
        raise HTTPException(404, "Subscription not found")

    updates = ["is_confirmed=1"]
    params = []
    if req.name:
        updates.append("name=?")
        params.append(req.name)
    if req.amount:
        updates.append("amount=?")
        params.append(req.amount)
    if req.frequency:
        updates.append("frequency=?")
        params.append(req.frequency)

    params.append(req.sub_id)
    conn.execute(f"UPDATE subscriptions SET {', '.join(updates)} WHERE id=?", params)
    conn.commit()
    conn.close()

    return {"status": "confirmed"}


@app.get("/api/stats/{user_id}")
async def get_stats(user_id: str):
    """Get user subscription stats — total spend, counts, etc."""
    conn = get_db()
    subs = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? AND is_confirmed=1",
        (user_id,),
    ).fetchall()
    logs = conn.execute(
        "SELECT COUNT(*) as scans, SUM(emails_processed) as emails, SUM(subs_found) as found FROM scan_log WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()

    total_monthly = 0
    total_yearly = 0
    for s in subs:
        amt = s["amount"] or 0
        freq = s["frequency"] or "monthly"
        if freq == "yearly":
            total_yearly += amt
        elif freq == "quarterly":
            total_yearly += amt * 4
        elif freq == "weekly":
            total_yearly += amt * 52
        else:
            total_monthly += amt

    # Perceived vs actual gap (the viral hook)
    perceived_monthly = 500  # Average user thinks ~₹500/mo on subs
    actual_monthly = total_monthly + (total_yearly / 12)

    return {
        "total_subs": len(subs),
        "total_monthly_spend": round(actual_monthly, 2),
        "total_yearly_spend": round(actual_monthly * 12, 2),
        "estimated_perceived_spend": perceived_monthly,
        "surprise_gap": round(actual_monthly - perceived_monthly, 2),
        "surprise_gap_pct": round(((actual_monthly - perceived_monthly) / perceived_monthly) * 100, 0) if perceived_monthly > 0 else 0,
        "by_category": {
            cat: round(sum(s["amount"] or 0 for s in subs if s["category"] == cat), 2)
            for cat in set(s["category"] for s in subs)
        },
        "scans_completed": logs["scans"] or 0,
        "emails_scanned": logs["emails"] or 0,
        "subs_detected": logs["found"] or 0,
    }


@app.delete("/api/subscriptions/{sub_id}")
async def delete_subscription(sub_id: str):
    conn = get_db()
    conn.execute("DELETE FROM subscriptions WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
