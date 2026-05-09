"""waitlist.py — Drop-in module for /api/waitlist endpoint.

Add to main.py:
    from waitlist import router as waitlist_router
    app.include_router(waitlist_router)

Or copy the body of register_waitlist() directly into main.py.

Security:
  - Honeypot validation
  - Rate-limited via slowapi
  - Email validation
  - Idempotent (409 on duplicate, not silent dedupe)
"""

import re
from datetime import datetime, timezone
from typing import Optional
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, EmailStr, field_validator
import sqlite3

router = APIRouter()

# Reuse the limiter and db() from main.py — these imports are placeholders.
# In production: from main import limiter, db
# (or copy the whole block into main.py and remove this file)


_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$')


class WaitlistRequest(BaseModel):
    email:    str          = Field(..., min_length=5, max_length=254)
    hp_check: Optional[str] = Field(default="", max_length=200)  # honeypot

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v


def init_waitlist_table(db_func):
    """Call once on app startup. db_func is the context manager from main.py."""
    with db_func() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT (datetime('now')),
                ip_hint    TEXT
            );
        """)
        conn.commit()


# ── Endpoint (paste this into main.py with the @app.post decorator) ──

# @app.post("/api/waitlist")
# @limiter.limit("5/hour")  # IP-based, generous enough for real users
async def join_waitlist(request: Request, body: WaitlistRequest, db_func):
    """Add an email to the waitlist. Returns 200 OK or 409 if duplicate."""

    # Honeypot — bot caught
    if body.hp_check:
        # Silently "succeed" — don't tell the bot
        return {"status": "ok"}

    # Use a hashed IP hint for abuse tracking (no PII)
    import hashlib
    ip = request.client.host if request.client else "unknown"
    ip_hint = hashlib.sha256(ip.encode()).hexdigest()[:16]

    try:
        with db_func() as conn:
            conn.execute(
                "INSERT INTO waitlist (email, ip_hint) VALUES (?, ?)",
                (body.email, ip_hint),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        # Email already in waitlist
        raise HTTPException(409, "Email already on the list")

    # TODO: send confirmation email via Resend / Postmark / Mailgun
    # For MVP we just store and notify manually.

    return {"status": "ok"}


# ── For the laziest copy-paste: the full block to add to main.py ──

WAITLIST_CODE_BLOCK = '''
# Add near other imports:
import hashlib

# Add near other Pydantic models:
_EMAIL_RE = re.compile(r"^[^\\s@]+@[^\\s@]+\\.[^\\s@]{2,}$")

class WaitlistRequest(BaseModel):
    email:    str = Field(..., min_length=5, max_length=254)
    hp_check: Optional[str] = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v

# Add to init_db() executescript:
#     CREATE TABLE IF NOT EXISTS waitlist (
#         id         INTEGER PRIMARY KEY AUTOINCREMENT,
#         email      TEXT NOT NULL UNIQUE,
#         created_at TEXT DEFAULT (datetime('now')),
#         ip_hint    TEXT
#     );

@app.post("/api/waitlist")
@limiter.limit("5/hour")
async def join_waitlist(request: Request, body: WaitlistRequest):
    if body.hp_check:
        return {"status": "ok"}
    ip = request.client.host if request.client else "unknown"
    ip_hint = hashlib.sha256(ip.encode()).hexdigest()[:16]
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO waitlist (email, ip_hint) VALUES (?, ?)",
                (body.email, ip_hint),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Email already on the list")
    return {"status": "ok"}
'''
