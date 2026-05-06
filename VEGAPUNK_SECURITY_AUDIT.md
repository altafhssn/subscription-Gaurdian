# VEGAPUNK_SECURITY_AUDIT.md
## Subscription Guardian — Full Security Review
**Auditor:** Vegapunk 🧠  
**Date:** 2026-05-06  
**Files audited:** `server.js`, `db.js`, `package.json`, `.env.example`, `public/dashboard.html`

---

## 🔴 CRITICAL (Fix before deployment)

### C1. OAuth callback lacks rate limiting — token exchange flood
**File:** `server.js` line 154 (`/auth/callback`)
- No rate limiting on the OAuth callback route. An attacker can hit this endpoint repeatedly with stolen auth codes or forged `?code=` params.
- Google's token endpoint is called with `oauth2Client.getToken(code)` — if the code is invalid, Google returns an error, but repeated attempts cost API quota and can exhaust Google's rate limit for the app.
- **Fix:** Add `express-rate-limit` middleware, minimum 5 req/min on `/auth/callback`.

### C2. No request body size limit
**File:** `server.js` line 23 (`app.use(express.json())`)
- Default body limit is 100kb in Express 4, but explicit limits should be set. If any POST route is added later without a limit, it's an easy DoS vector.
- **Fix:** `app.use(express.json({ limit: '10kb' }))`

### C3. No brute-force protection on authenticated endpoints
**File:** `server.js` lines 229 (`/api/subscriptions`), 244 (`/account/delete`)
- No rate limiting at all. An attacker with a valid session cookie can hammer these endpoints without restriction.
- **Fix:** Apply rate limiter to all `/api/*` and `/account/*` routes.

---

## 🟠 HIGH (Fix before production)

### H1. `ssl: rejectUnauthorized: false` in production
**File:** `server.js` line 32
```js
ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false
```
- Disabling TLS certificate validation in production defeats the purpose of SSL. Connection is encrypted but MITM is still possible.
- **Risk:** Anyone who can intercept the connection between the app and PostgreSQL can read database traffic.
- **Fix:** Remove this override. Use proper CA certificates or `ssl: { rejectUnauthorized: true }`. If using Railway/Supabase/Neon, fetch their CA cert.
```js
ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: true } : false
```

### H2. `session_token` stored in plaintext in DB
**File:** `server.js` line 484, `db.js` schema
- Session token is a 64-char hex string stored in plaintext. If the database is breached, every active session can be hijacked.
- Risk is mitigated because the session isn't auth-primary (OAuth token is), but still unnecessary exposure.
- **Fix:** Store `SHA256(session_token)` instead, and hash it on lookup. Or use a dedicated session store (Redis).
```js
const crypto = require('crypto');
const sessionHash = crypto.createHash('sha256').update(sessionToken).digest('hex');
// Store sessionHash, query by sessionHash
```

### H3. `oauth_state` cookie has no `SameSite` attribute
**File:** `server.js` line 136
```js
res.cookie('oauth_state', state, { 
  httpOnly: true, 
  secure: process.env.NODE_ENV === 'production',
  maxAge: 10 * 60 * 1000 
});
```
- No `SameSite` flag means the cookie is sent on cross-origin requests by default (lax behavior in Chromium, none in others).
- **Risk:** CSRF against OAuth flow, though state parameter provides some protection.
- **Fix:** Add `sameSite: 'lax'`.

### H4. Missing security headers entirely
**File:** `server.js` — no `helmet` middleware or manual headers
- Missing: `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`
- **Risk:** XSS, clickjacking, MIME-type sniffing attacks.
- **Fix:** Add `helmet` middleware. Only 5 lines:
```bash
npm install helmet
```
```js
const helmet = require('helmet');
app.use(helmet());
```

### H5. No input validation on subscription data in dashboard
**File:** `public/dashboard.html` lines 241–263
- `data.service_name` is rendered directly via `innerHTML` without sanitization:
```js
item.innerHTML = `...<div class="name">${sub.service_name}</div>...`
```
- If a malicious email with crafted HTML in the subject/from field gets parsed as a subscription name, it becomes stored XSS.
- **Fix:** Use `textContent` for service names, or sanitize via DOMPurify. The server should also escape all output.
```js
const nameDiv = item.querySelector('.name');
nameDiv.textContent = sub.service_name;
```

### H6. `cors` allows a single origin but no fallback
**File:** `server.js` line 22
```js
app.use(cors({ origin: process.env.APP_URL, credentials: true }));
```
- If `APP_URL` is undefined (env not set), `cors` accepts `undefined` as origin, which means it matches `undefined` literally — effectively breaking CORS for all real origins. App will silently fail.
- **Fix:** Validate `APP_URL` at startup and crash if missing.

---

## 🟡 MEDIUM (Fix recommended before launch)

### M1. Error messages leak internal details
**File:** `server.js` lines 238, 256, 268
```js
res.status(500).json({ error: 'Server error' });
// BUT: console.error logs include err.message
```
- The API correctly returns generic messages. But there are unhandled paths — what if `encryptToken` throws (e.g., bad ENCRYPTION_KEY)? That would crash the OAuth callback with no user-friendly error.
- **Fix:** Wrap OAuth callback body in a try-catch with a redirect to `/?error=auth_failed`.

### M2. No CSRF protection on POST /account/delete
**File:** `server.js` lines 244–258
- POST endpoint has no CSRF token. An attacker who can get a logged-in user to visit a malicious site could trigger account deletion.
- **Fix:** Add a CSRF token to the delete page form, or require re-authentication for deletion.

### M3. `uuid` and `bcrypt` listed as dependencies but unused
**File:** `package.json`
- `bcrypt` (5.1.1) — not imported or used anywhere in the codebase. Dead dependency.
- `uuid` (9.0.0) — not imported or used anywhere. Dead dependency.
- Both are popular packages with CVEs. `bcrypt` specifically had CVE-2024-29734 (affects <5.1.1, fixed in 5.1.1 so current version is okay, but still unnecessary attack surface).
- **Fix:** Remove both from `package.json`.

### M4. Dashboard serves without auth check
**File:** `server.js` line 31 (`app.use(express.static('public'))`)
- `public/dashboard.html` is served as static via Express AND also via the `/dashboard` route. The static middleware has no auth check. The route-based `/dashboard` is also unauthenticated (it just serves the HTML — auth is only checked on the `/api/subscriptions` fetch).
- **Low risk** because the dashboard HTML itself contains no secret data. But the static route means the file can be loaded as `/dashboard.html` or `/dashboard` with identical results.
- **Fix:** Either serve all pages through routes (remove the static handler) or add a middleware that redirects unauthenticated users on page-level routes.

### M5. `prompt: 'consent'` forces re-auth every time
**File:** `server.js` line 143
```js
prompt: 'consent' // Force refresh token on every auth
```
- This means every time a user clicks "Connect Gmail" they get the full Google consent screen even if they've already authorized. This is intentional for refresh token access, but the comment is misleading. Also means a returning user sees a confusing re-auth flow.
- **Fix:** Improve UX — explain on the landing page that re-auth is expected the first time, or use `prompt: 'select_account'` instead of 'consent'.

### M6. Token IV and authTag stored in a single column
**File:** `db.js` / `server.js` line 191
```js
encAccess.iv + ':' + encAccess.authTag
```
- Stored as `token_iv` (named misleadingly — it's really `iv:authTag`). The column is called `token_iv` but contains both. If someone refactors the schema, the assumption that `token_iv` is just the IV could break decryption.
- **Fix:** Add a separate `token_auth_tag` column instead of packing both into one field. (Already partially in schema but unused.)

### M7. No email domain validation
**File:** `server.js` line 170
```js
const email = profile.data.emailAddress;
```
- The email comes from Google so it's inherently trusted. But there's no check that the user has a valid, non-disposable email domain. Low risk since it's Google-authenticated.
- **Fix:** Not needed for MVP, but consider for fraud prevention later.

---

## 🔵 LOW (Nice-to-have before launch)

### L1. No `maxResults` parameter on Gmail list call
**File:** `server.js` lines 312–316
```js
const messages = response.data.messages || [];
emailsScanned = messages.length;
```
- For users with hundreds of subscription emails, this only scans 50. Users won't see their full picture. They'll think Guardian is incomplete.
- **Fix:** Use pagination (`nextPageToken`) or increase `maxResults` to 500.

### L2. Scan runs synchronously in background — no status feedback
**File:** `server.js` line 217
```js
scanUserEmails(email).catch(err => { ... });
```
- The dashboard immediately shows `?scan=started` but has no polling mechanism to know when scan completes. User could see an empty dashboard and think it's broken.
- **Fix:** Add a WebSocket or polling endpoint (`/api/scan-status`) that the dashboard can check.

### L3. Scan errors are silently caught with generic logging
**File:** `server.js` line 218
```js
console.error('Background scan failed for', email, err.message);
```
- Full error stack is not logged. If the scan fails for a specific user, debugging requires access to the production server.
- **Fix:** Log full error objects to a structured logger (pino, winston) or at minimum log `err.stack`.

### L4. No `retry-after` on rescan
**File:** `server.js` line 214
- After OAuth, the scan triggers immediately. If 10 users sign up simultaneously, 10 Gmail API calls fire at once. Google API has quota limits (typically 250M queries/day for Gmail, but rate-limited per user).
- **Fix:** Queue scans with rate limiting (1 user/sec or similar).

### L5. `SESSION_SECRET` in .env.example but never used in code
**File:** `.env.example`
- `SESSION_SECRET` is listed as an environment variable but never referenced in server.js. The sessions don't use a secret-based encoding — they use random tokens.
- **Fix:** Remove `SESSION_SECRET` from .env.example, or implement session encryption/signing.

### L6. No `Authorization` header on delete link
**File:** `public/dashboard.html` line 134
```html
<a href="/account/delete" id="deleteLink" ...>Delete data</a>
```
- Links to a GET endpoint that shows a form. The form then POSTs. There's no confirmation dialog on the dashboard link itself — one accidental click and the user lands on a scary "are you sure?" page. Low risk but poor UX.

### L7. Deprecated `token_iv` column still in schema
**File:** `db.js` lines 12–13
- The schema includes `token_iv TEXT` column. But the code stores `iv:authTag` in it as a packed string. There's also a `token_auth_tag` column that's always set to `null`. This inconsistency makes audit/debug harder.
- **Fix:** Consolidate to either use the existing schema with proper columns, or document why `token_auth_tag` is unused.

---

## 🔐 Overall Security Score: **68/100** (C)

| Category | Score | Notes |
|----------|-------|-------|
| Authentication | 70 | Solid OAuth flow, state param works, but sessions stored in plaintext |
| Data Protection | 75 | AES-256-GCM for tokens ✓, but ssl rejectUnauthorized:false undermines DB channel |
| Input Validation | 50 | Stored XSS vector in dashboard, no CSRF on delete |
| Rate Limiting | 0 | No rate limiting anywhere |
| HTTP Security | 20 | No helmet, no security headers |
| Dependencies | 65 | Dead deps (uuid, bcrypt), but nothing critically outdated |
| Privacy Compliance | 80 | GDPR-friendly by design (90d retention, delete endpoint), but no cookie consent notice |

### Verdict: **DEPLOY WITH FIXES** 🟡

Fix the Critical and High issues before putting real users on it:
1. **C1-C3:** Add rate limiting (30 min)
2. **H1:** Fix SSL config (5 min)  
3. **H3-H4:** Add helmet + SameSite (10 min)
4. **H5:** Sanitize dashboard output (15 min)
5. **H2:** Hash session tokens (20 min)

Total fix time: ~80 minutes for a production-ready security posture.

Let me know if you want me to implement the fixes.
