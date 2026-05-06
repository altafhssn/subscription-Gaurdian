# Subscription Guardian — Complete User Flow

## Overview

1. User visits subscriptionguardian.com
2. Clicks "Connect Gmail — It's Free"
3. Google OAuth popup → "read-only access to Gmail"
4. User grants permission
5. Backend immediately scans last 6 months of receipts
6. User lands on dashboard showing all subscriptions found
7. Free tier: one-time scan, up to 10 subs
8. Guardian ($3/mo): monthly auto-scan, alerts, unlimited

---

## Step-by-Step (Technical Flow)

```
User clicks "Connect Gmail"
  ↓
GET /auth/gmail
  ↓
Generate random state (CSRF protection)
Set cookie oauth_state
Redirect to Google consent screen
  ↓
Google shows: "Subscription Guardian wants to read your Gmail"
Scope: gmail.readonly
Warning: "This app is not verified" (normal for <100 users)
  ↓
User clicks "Allow"
  ↓
Google redirects to /auth/callback?code=xxx&state=yyy
  ↓
Server verifies state matches cookie
  ↓
Server exchanges code for tokens
  ↓
Server gets user email from Google profile
  ↓
Server ENCRYPTS tokens with AES-256-GCM
  ↓
Server stores in PostgreSQL:
  - email, google_id
  - encrypted_access_token, encrypted_refresh_token
  - token_iv, token_auth_tag
  - data_retention_date (NOW + 90 days)
  ↓
Server sets session cookie (httpOnly, 30 days)
  ↓
Redirects user to /dashboard?scan=started
  ↓
Background scanUserEmails() runs:
  - Searches Gmail: "receipt OR invoice OR subscription..."
  - Fetches up to 50 matching emails (last 6 months)
  - For each email, checks sender domain against known services
  - If match: extracts service_name, amount, billing_cycle
  - Stores in subscriptions table
  - If unknown: skips (user can add manually later)
  - Logs scan in scan_log table
  ↓
User sees dashboard with all subscriptions found
```

---

## Database Schema

```sql
-- Users table (encrypted tokens, auto-delete)
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  google_id VARCHAR(255),
  encrypted_access_token TEXT NOT NULL,
  encrypted_refresh_token TEXT,
  token_iv TEXT NOT NULL,         -- "iv:authTag" format
  token_auth_tag TEXT,
  plan VARCHAR(20) DEFAULT 'free',
  stripe_customer_id VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  last_scan_at TIMESTAMP,
  data_retention_date TIMESTAMP DEFAULT (NOW() + INTERVAL '90 days')
);

-- Subscriptions found per user
CREATE TABLE subscriptions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  service_name VARCHAR(255) NOT NULL,
  amount DECIMAL(10,2),
  currency VARCHAR(10) DEFAULT 'USD',
  billing_cycle VARCHAR(50),       -- monthly, yearly, weekly
  next_billing_date DATE,
  category VARCHAR(100),
  status VARCHAR(20) DEFAULT 'active',
  cancel_url TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Audit log for scans
CREATE TABLE scan_log (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  scanned_at TIMESTAMP DEFAULT NOW(),
  emails_scanned INTEGER DEFAULT 0,
  subscriptions_found INTEGER DEFAULT 0,
  new_subscriptions INTEGER DEFAULT 0
);
```

---

## Compliance Checklist (Built Into This Backend)

| Requirement | How it's handled |
|---|---|
| Privacy policy | `/privacy` endpoint |
| Terms of service | `/terms` endpoint |
| Token encryption | AES-256-GCM (db.js) |
| Data deletion | POST /account/delete + CASCADE |
| Auto data purge | 90 day retention (cron-ready) |
| Business registration | Sole proprietorship (India) |
| Read-only scope | Only gmail.readonly requested |
| Token refresh | Auto-refresh on expiry |
| Audit log | scan_log tracks all scans |

---

## Immediate Next Steps

1. Register on Google Cloud Console → enable Gmail API
2. Create OAuth credentials (Web application type)
3. Get a domain (subscriptionguardian.com)
4. Deploy backend to Railway/Render
5. Set up PostgreSQL (Railway/Supabase free tier)
6. Update .env with your credentials
7. Run `npm install && npm start`
8. Test with your own Gmail
9. Add first beta users (add their emails to OAuth consent screen)
10. Start collecting feedback
