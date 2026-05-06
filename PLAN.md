# Subscription Guardian — Landing → Web App Migration

## Current State

- ✅ **server.js** — Full Express backend with OAuth, Gmail scanning, DB, API, privacy
- ✅ **landing/index.html** — Marketing landing page (dark mode, emoji-free)
- ❌ No dashboard UI (the `/dashboard` route doesn't render anything useful yet)
- ❌ server.js serves `public/` dir but it's empty
- ❌ Landing is a separate server, not talking to backend

## Day 1 Plan: Wire Landing to Backend

### 1. Restructure files

```
subscription-guardian-landing/
├── server.js              # Express backend (already complete)
├── index.html             → becomes main HTML template
├── public/
│   └── dashboard.html     → NEW: post-login dashboard
├── db.js                  # DB helpers
├── .env.example
├── package.json
```

### 2. Landing page changes (index.html)
- Replace `onclick="alert(...)"` on CTA with real OAuth redirect
- CTA button → links to `/auth/gmail` on server
- Add session-aware state: show different content when logged in
- Keep current dark theme and SVGs

### 3. Dashboard page (new)
- Post-OAuth redirect target: `/dashboard?scan=started`
- Pull data from `/api/subscriptions` 
- Show:
  - Total monthly spend (big number)
  - Surprise gap: "You think £X — Actually £Y"
  - Subscription list sorted by cost
  - Category breakdown
  - Upgrade prompt (Free → Guardian £3.99/mo)

### 4. Server.js additions (minor)
- Serve dashboard.html from public/
- Add session middleware (proper session store, not the hacky LIMIT 1)
- Add GBP detection to the scanner (currently USD regex)
- Add more UK-specific services (Monzo, Revolut, etc.)

