# VEGAPUNK ARCHITECTURE REVIEW: Subscription Guardian Delivery Mechanism

**Author:** Vegapunk (Technical Research Specialist)
**Date:** 2026-05-06
**Subject:** Chrome Extension vs. Web App (SaaS) — Which delivery mechanism for Subscription Guardian?

---

## Executive Summary

Subscription Guardian (SG) currently ships as a **Manifest V3 Chrome Extension + FastAPI backend**. The core question: should it stay this way, or pivot to a standalone web app (SaaS)?

**TL;DR answer:** The web app should be the **primary delivery mechanism** for the MVP and go-to-market. The Chrome extension should be retained as a **companion/optional addition** for convenience features (quick popup, toolbar badge notifications). Lead with the web app for the UK launch because it solves device-agnostic access, background scanning reliability, trust friction, and scalability — all critical for a Gmail-scanning product in a post-Unroll.me world.

---

## 1. Chrome Extension: Pros & Cons

### 1.1 Chrome Market Share in the UK

| Metric | Value |
|--------|-------|
| UK Chrome desktop market share (Apr 2025–Apr 2026) | **~50.94%** |
| UK Chrome + Edge (Chromium) combined | **~62%** |
| Global Chrome desktop share | **~68%** |
| UK Safari share | **~29.4%** |
| UK users on non-Chromium browsers | **~38%** (Safari + Firefox + others) |

**Implication:** ~50% of UK desktop users are on Chrome. But that still leaves ~50% on Safari, Firefox, or Edge (non-Chromium-implemented browsers). A Chrome-exclusive extension **automatically excludes half the addressable market**. Worse, mobile usage is dominated by Safari on iOS (where Chrome is a reskinned WebKit) and extensions don't work at all on mobile Chrome.

### 1.2 Extension Install Friction

**Install process:** User must visit Chrome Web Store → click "Add to Chrome" → confirm permissions popup → wait for download → pin the extension → complete onboarding. Each step introduces drop-off.

**Observed conversion data from the extension ecosystem:**
- Typical install-to-active-user ratio for Chrome extensions: **10–20%** (per CWS analytics discussions)
- Extensions requiring signup have **~30% uninstall rates** shortly after install (Indie Hackers data)
- Each permission warning causes measurable drop-off — Gmail access is one of the most permission-heavy warnings

**The friction is real and well-documented.** Every extra step (install, permissions, pinning, signup) compounds the churn. Contrast with a web app: user clicks a link, sees a Google login button, and they're in.

### 1.3 Gmail OAuth: Extension vs. Web App

| Aspect | Chrome Extension | Web App |
|--------|-----------------|---------|
| **Auth mechanism** | `chrome.identity.getAuthToken()` — seamless, uses user's Chrome login | Standard OAuth 2.0 Authorization Code flow with PKCE |
| **User flow** | One-click if already signed into Chrome; no redirect tab needed | Redirect to Google OAuth consent screen, then back to app |
| **Token storage** | Chrome manages silently via Identity API | Server-side with refresh tokens in secure storage |
| **OAuth verification required** | **Same** — Gmail sensitive scopes trigger Google's OAuth verification regardless of client type | **Same** |
| **Token refresh** | Chrome handles automatically as long as the user is signed into Chrome | Requires server-side refresh token management |
| **Advanced Protection users** | Blocked (Advanced Protection disables all third-party Gmail OAuth for both) | Blocked |

**Verdict:** The `getAuthToken()` API is genuinely smoother for the initial auth flow — it's nearly frictionless for users already signed into Chrome. However, this is a **one-time advantage** that matters mostly for first-run onboarding. For renewal/re-authentication, both work fine. The web app's more complex OAuth flow can be mitigated with good UX (a single "Sign in with Google" button).

### 1.4 Manifest V3 Limitations (Critical)

This is the **biggest technical concern** with the extension approach. Manifest V3 (mandatory since June 2024 for new extensions, phased in for existing ones) introduced several painful constraints:

**1. Service Worker Timeouts**
- Chrome terminates the service worker after **30 seconds of inactivity**
- Maximum extension lifespan for background tasks: **~5 minutes** (via extended `chrome.alarms` but with unreliable persistence)
- Workarounds exist (keep calling async `chrome` APIs to reset the idle timer) but they're fragile hacks

**For Subscription Guardian this means:**
- Scanning 5,000+ emails for subscriptions is not possible in a single background session
- Must either: (a) chunk scanning across multiple alarm-driven invocations, (b) do all scanning on the server side with the extension as a thin client, or (c) rely on the popup/options page being open to keep the worker alive
- Background scans are inherently unreliable — if the user closes their browser, scanning stops

**2. No Remotely Hosted Code**
- All code must be bundled in the extension package
- Cannot push server-side logic updates without a Chrome Web Store review
- Makes it harder to iterate on the detection engine without full extension releases

**3. DOM Access Restrictions**
- Cannot directly inject scripts into Gmail's web interface (not that SG needs this, but it limits future expansion)
- Content scripts have separate execution contexts

### 1.5 Chrome Web Store Review Times & Approval Rates

| Data Point | Value |
|-----------|-------|
| Typical first-time review | **4–14 days** (highly variable) |
| Common reported range (2024–2026) | 3 days to 3+ weeks |
| OAuth verification waiting time | **8+ weeks** (documented case as recent as Jan 2026) |
| Extensions with sensitive scopes | Face stricter scrutiny — Google reviews code access patterns |
| Update review time | Usually faster (1–3 days) but still a gate |
| Approval rate | Not published, but extensions requesting Gmail/sensitive scopes are **frequently rejected** on first submission |

**Key risk:** If Google rejects the extension during review (or OAuth verification drags on for 8+ weeks), your launch timeline is **blocked**. You cannot iterate or ship features without going back through this process.

**Hot issue (Apr 2026):** Chrome Web Store reviewers now check whether OAuth verification is complete before approving extensions with sensitive scopes. This creates a **two-gate dependency**: you can't get extension published without OAuth verification done, and OAuth verification requires a working app with a privacy policy and terms of service. It's a chicken-and-egg that adds weeks to launch.

### 1.6 Auto-Update Advantages

Extensions auto-update every ~5–6 hours via Chrome's built-in mechanism. This is **genuinely good** — push a new version to CWS, and within a day, most users are on the latest version.

**Counterpoint:** For a server-client architecture (SG's current model), the backend can update independently of the extension. The detection logic lives on the FastAPI server. So auto-update advantages are mostly for UI changes and permission updates, not for core detection logic.

### 1.7 User Trust: Extensions vs. Web Apps for Gmail Access

**This is a major trust issue for the UK market.**

**The Unroll.me scar:** In 2017, Unroll.me was exposed for selling anonymized inbox data (Uber/Lyft receipts) to its parent company Slice. The backlash was severe — NYT, Guardian, CNBC, Mashable all covered it. Unroll.me's CEO was "heartbroken" that users found out. This created a **category trust deficit** for any product that scans Gmail.

**Aftermath for the category:**
- Unroll.me is now seen skeptically despite being a web service (not extension) that simply asked for Gmail OAuth access
- Users are increasingly wary of both extensions and web apps that request Gmail access
- The Chrome extension spyware scandals of 2024–2025 (Malwarebytes reported "millions spied on by malicious extensions" in July 2025) have **further eroded trust in extensions specifically**
- Extensions have broader permission models (can read browser data on all sites) — power users are increasingly conservative about installing them

**Trust comparison:**

| Factor | Chrome Extension | Web App (SaaS) |
|--------|-----------------|----------------|
| **Permission scope** | Can read all site data (if declared), access browsing history | Limited to OAuth-granted Gmail scope only |
| **Perception** | High risk — recent spyware coverage has damaged extension trust | Moderate risk — seen as comparable to any "sign in with Google" SaaS |
| **Transparency** | User can inspect permissions in chrome://extensions | User can revoke access in Google Account settings |
| **Revocation** | One-click uninstall from toolbar | One-click revoke from Google Account → Apps with access |
| **Notable factor** | Extensions remain installed after OAuth token is revoked; user must also uninstall | Revoking OAuth immediately severs access |

**Verdict:** Web apps have a **moderate trust advantage** over extensions for Gmail access, purely because the extension attack surface is larger and more publicized. Neither is fully trusted — but the web app carries less negative baggage.

---

## 2. Web App (SaaS): Pros & Cons

### 2.1 Zero Friction

Web app onboarding: **Send link → Click → "Sign in with Google" → Done.** No install, no permissions popup, no Chrome Web Store, no pinning, no Chrome dependency. For a product that already requires Gmail OAuth (which is inherently permission-heavy), removing the extension install step is the single biggest UX win.

**Conversion funnel comparison:**

| Step | Chrome Extension | Web App |
|------|-----------------|---------|
| 1. Discovery | CWS listing OR website link | Website link |
| 2. Install | Click "Add to Chrome" | (skipped) |
| 3. Permission warning | Scary "Read and change your data on all websites" popup | (skipped) |
| 4. Chrome toolbar | Must pin extension | (skipped) |
| 5. Sign in | Click extension → OAuth | Click "Sign in with Google" on landing page |
| 6. Scan | Wait for background scan | Wait for server scan (can leave page) |

### 2.2 Device-Agnostic Access

A web app works on:
- **Chrome, Safari, Firefox, Edge** — all desktop browsers
- **iOS Safari, Android Chrome** — mobile browsers (extensions don't work on mobile)
- **Any device** with a browser

UK mobile market share is ~60% of all web traffic. A Chrome-only extension misses mobile users entirely. A web app captures them.

**Additionally:** A web app allows the user to check their dashboard from work, home, or phone. An extension locks them to Chrome on their personal desktop.

### 2.3 Background Scanning: Server Cron vs. Extension Service Worker

**This is the decisive technical advantage for web app approach:**

| Feature | Extension (Service Worker) | Web App (Server Cron) |
|---------|---------------------------|----------------------|
| Can scan all historical emails | Yes, but in unreliable chunks | **Yes, reliably** |
| Recurring scans (daily/weekly) | Yes, via `chrome.alarms`, but reliability is **poor** — worker can be terminated before completion | **Yes, via server-side cron job — deterministic** |
| Scanning while browser is closed | **No** — worker dies with the browser | **Yes** — server never sleeps |
| Scanning while user is offline | **No** | Server handles independently |
| Scanning large mailboxes (10k+ emails) | **Unreliable** — timeout constraints | **No issue** — pagination works naturally |
| Fresh token requirement | Must re-auth periodically when Chrome signs user out | Persistent refresh tokens work as long as user hasn't revoked |
| Can alert user of new subscriptions | Must use `chrome.notifications`, only works if browser is running | Can email, SMS, push notification |

**The extension service worker is fundamentally unfit for reliable Gmail scanning.** Google has made this clear with MV3 — service workers are designed for ephemeral tasks triggered by events, not for batch processing of thousand-message inboxes. Every SG scan of a new user (especially with years of receipts) will be a race against the 5-minute timeout.

### 2.4 Google OAuth Verification: Same for Both

This is critical to understand: **the OAuth verification process is identical for extensions and web apps.** Both require:
1. Google Cloud Project with OAuth consent screen configured
2. Brand verification (user count, privacy policy URL, terms of service URL)
3. Restricted scope verification (Gmail sensitive scopes like `https://mail.google.com/` or `https://www.googleapis.com/auth/gmail.readonly`)
4. Security assessment (may require a third-party pentest if over 100 users)
5. Waiting period (typically 3–8+ weeks)

**There is zero OAuth advantage to being an extension.** The only difference is that extensions additionally need Chrome Web Store review (another gate).

### 2.5 GDPR Compliance Differences

For UK users (post-Brexit UK GDPR), the obligations are:

| Requirement | Chrome Extension | Web App |
|------------|-----------------|---------|
| Privacy notice | Required (both) | Required (both) |
| Data Processing Agreement | Required if using third-party infra | Required if using third-party infra |
| Data minimization | Same — only scan for subscription receipts | Same |
| User consent | OAuth consent screen covers this | OAuth consent screen covers this |
| Right to erasure | Need to handle stored data deletion | Need to handle stored data deletion |
| **Server-side data storage** | Already stores data on server | Already stores data on server |

**No material GDPR difference.** Both store user's subscription data on the same backend server. The privacy model is identical. The extension itself doesn't add GDPR complexity (it's a thin client).

One minor edge: a web app serving UK users could use UK-based servers (digitalocean London region, for example) more naturally than a Chrome extension that runs locally. But SG already has a server backend, so this is moot.

### 2.6 Email Reports & Alerts

A web app can send:
- **Weekly digest emails** summarizing subscriptions
- **Pre-renewal alerts** ("Netflix charging you £10.99 tomorrow")
- **Price increase notifications**
- **Annual subscription reminders**
- **Unsubscribe recommendations**

The Chrome extension can also trigger Gmail draft emails or use the extension as a notification surface — but email is better (push-based, works even when browser is closed).

---

## 3. Key Technical Constraints

### 3.1 Gmail API Quotas: Identical

As of 2026, the Gmail API enforces:

| Quota Type | Limit |
|-----------|-------|
| Per minute per project | 1,200,000 quota units |
| Per minute per user per project | 6,000 quota units |
| Per day per project (free threshold) | 80,000,000 quota units |

**Method costs:**
- `messages.list`: 5 units per call
- `messages.get`: 20 units per email
- `threads.list`: 10 units per call

**For a typical user scan:**
- List query (say 50 threads per page): ~5 units
- Get 50 threads: ~50 × 40 = 2,000 units (threads.get)
- Total per user per scan: ~2,200 units

At 6,000 per minute per user, you can scan one user ~2.7 times per minute. At 1,200,000 per project per minute, with 600 active users scanning simultaneously (unlikely for MVP), you'd hit the project limit first. **For early-stage, quotas are irrelevant** — you won't come close to these limits.

**Important:** Gmail API recently announced (2026) a daily billing threshold of 80M units, with charges coming after that. Full billing details coming later in 2026 with 90 days' notice. This will eventually matter but not for an MVP.

**Bottom line:** Same limits regardless of whether requests come from an extension or a web app.

### 3.2 Can a Web App Scan Emails in the Background?

**Yes — and this is the killer feature.**

Flow:
1. User signs in via OAuth on the web app
2. Server receives an **offline refresh token** (requires `access_type=offline` and `prompt=consent`)
3. Server can call Gmail API 24/7 without the user being online
4. Initial scan runs on the server immediately (no browser dependency)
5. Weekly/daily rescan runs via cron job
6. Results are stored and served via the web dashboard

**This is impossible with a pure Extension approach** because the chrome.identity flow doesn't reliably give server-side refresh tokens (it's designed for client-side use). The service worker dies when the browser closes, so rescanning stops.

**Current SG architecture:** The extension calls the FastAPI backend, which then calls the Gmail API. This actually means the backend already does the scanning. But the trigger flow is extension → backend, meaning scanning is still gated by the extension being active. If SG moves to a web app, the trigger flow becomes user login → backend directly → cron schedule, removing the browser dependency entirely.

### 3.3 Chrome Identity API Advantage

`chrome.identity.getAuthToken()` is genuinely smoother:
- One-click auth if user is signed into Chrome
- No redirect URL configuration (extension ID is fixed)
- Silent token refresh handled by Chrome

**But:** This only works for Google services, and the token is scoped to the extension's client ID. To use it with the backend, SG currently sends the token to the FastAPI server, which then impersonates the user. This is a **less clean pattern** than server-side OAuth with refresh tokens.

**If SG moves to web app:**
- Standard OAuth 2.0 with PKCE
- Slightly more complex initial setup (one-time)
- But much cleaner architecture long-term
- Works on any browser, any device

### 3.4 Background Scanning Reliability

| Scenario | Extension Service Worker | Web App Server Cron |
|----------|-------------------------|---------------------|
| User hasn't opened Chrome in 3 days | ❌ No scan happens | ✅ Scan runs on schedule |
| User has 15,000 emails | ⚠️ Unlikely to complete in time; chunking needed | ✅ Paginated scan completes reliably |
| User opens browser at 3 AM for quick check | ❌ Worker starts scanning but may not finish | ✅ No impact — server handles it |
| User changes password | ⚠️ Extension token invalidates; requires user to open extension and re-auth | ✅ Server gets 403, sends user re-auth email |
| Weekly rescan | ⚠️ Unreliable — depends on browser being open at alarm time | ✅ Guaranteed weekly execution |
| Price change detection | ⚠️ Must poll on service worker wake | ✅ Server can check and alert immediately |

---

## 4. Real-World Examples

### 4.1 Rocket Money (Truebill)

**What they do:** Subscription tracking primarily via **bank transaction scanning**, not Gmail. Users link bank accounts via Plaid (and similar) for automatic categorization of recurring charges.

**Delivery mechanism:** **Mobile app (iOS + Android) + Web dashboard.**
- Not a Chrome extension
- Not scanning Gmail
- Bank-level linking (higher trust barrier than Gmail)
- ~$3.4B valuation at peak
- Monetization: Freemium with cancellation concierge

**Key takeaway:** Rocket Money chose the **most trusted channel possible** (direct bank linking through Plaid) with a mobile+web presence. They avoided the extension model entirely. Their trust pitch: "We access your transactions, not your email." After Unroll.me, Gmail scanning is a harder sell.

### 4.2 GhostSweep

**What they do:** Account/subscription discovery by scanning Gmail or Outlook inboxes.

**Delivery mechanism:** **Web app only** (ghostsweep.com — sign in with Gmail or Outlook).
- No Chrome extension
- Proactive about privacy/trust messaging on their site
- Claims "transient, zero-storage analysis"
- Targets the same problem as Subscription Guardian

**Key takeaway:** A direct competitor that chose web app only. They're marketing their zero-storage claim heavily. SG would be competing against this with an extension — and GhostSweep has the simpler onboarding.

### 4.3 Trackit

**What they do:** Subscription tracker that connects to Gmail to find hidden subscriptions.

**Delivery mechanism:** **iOS app** (not web, not extension).
- Links Gmail through OAuth
- Uses mail-level scanning from the app
- Just launched (early 2026)

**Key takeaway:** Even a mobile-native app is preferred over an extension. Users download the app from the App Store (which has a trust halo) and then connect Gmail. The store provides curation trust that Chrome Web Store doesn't fully replicate.

### 4.4 Unroll.me — The Cautionary Tale

**Original format:** **Web service** (sign in via Gmail OAuth on their website), later added a Chrome extension as a convenience layer.

**The 2017 scandal:**
- Users signed up expecting email unsubscription
- Unroll.me was selling anonymized inbox data to its parent Slice (Uber/Lyft receipts → market analytics)
- Users only discovered this from media reports, not in-app disclosures
- CEO claimed "heartbroken" — but the damage was done
- Resulted in **existential trust crisis** for the entire "scan-my-email" category

**How they handled (poorly):**
- Privacy policy did disclose data usage — in dense legal language
- No prominent in-app consent for data monetization
- Users felt betrayed because the service seemed "free" without explaining the monetization model

**Lessons for Subscription Guardian:**
1. **Transparency is paramount** — clearly explain what data is accessed and what happens to it
2. **Never sell email data** — this is table-stakes trust
3. **Monetize the value, not the data** — charge users for the subscription tracking, don't mine their inbox
4. **Privacy-first positioning is a competitive advantage** — lean into it
5. **Avoid any association with Unroll.me's model** — explicitly state "we don't read, store, or sell your email content"

### 4.5 What About the Gmail Add-on Path?

A third option exists: **Google Workspace Add-ons** (formerly Gmail Add-ons). These live inside the Gmail UI itself.

**Pros:**
- Native Gmail integration — users stay in their inbox
- Works on Gmail web on any browser
- Google's own platform (less likely to be deprioritized)

**Cons:**
- Limited UI space (sidebar widget)
- Cannot do background processing without a server backend
- Requires separate Workspace Marketplace listing
- Less discovery than Chrome Web Store

**Verdict:** Viable as a secondary channel (for power users who want inline subscription info in their Gmail), but not a replacement for the primary app.

---

## 5. Final Recommendation

### 5.1 Primary Decision: Lead with Web App (SaaS)

**Recommendation:** Make the web app (SaaS) the **primary delivery mechanism**. The Chrome extension should become **supplementary — a companion for quick access**, not the core product.

**Rationale:**

| Factor | Winner | Why |
|--------|--------|-----|
| Reach | **Web app** | Works on Chrome (50%), Safari (29%), Edge, Firefox, mobile |
| Trust | **Web app** | Post-Unroll.me + extension spyware scandals make Gmail-scraping extensions suspect |
| Scan reliability | **Web app** | Server cron > service worker. Not even close. |
| Onboarding friction | **Web app** | No install, no permission popup, no pinning |
| Development velocity | **Web app** | No CWS review gate; push daily |
| OAuth complexity | **Tie** | Same verification process required for both |
| Gmail API quotas | **Tie** | Identical quotas regardless of client type |
| Mobile support | **Web app** | Extensions don't work on mobile |
| Auto-updates | **Extension** | Chrome handles it, but backend updates are independent anyway |
| Quick access | **Extension** | Toolbar badge + popup is genuinely convenient |
| Offline access | **Extension** | Can show cached dashboard when offline |

**Score: Web app 8/10, Extension 5/10.**

### 5.2 Recommended Architecture

```
PRIMARY: Web App (SaaS)
├── Frontend (React/Next.js/Vue — responsive web)
│   ├── Landing page / marketing site
│   ├── Dashboard (subscription overview, spend analysis)
│   ├── Settings (notification prefs, account management)
│   └── "Sign in with Google" OAuth flow
│
├── Backend (existing FastAPI — largely reusable)
│   ├── Gmail API scan engine (existing, unchanged)
│   ├── Subscription detection engine (existing, unchanged)
│   ├── Cron scheduler (new — weekly scans)
│   ├── Notification engine (new — email alerts)
│   └── Data model (existing SQLite → upgrade to PostgreSQL for scale)
│
└── Infrastructure
    ├── UK/EU server region (GDPR compliance)
    ├── Email service (SendGrid/SES for notifications)
    └── PostgreSQL (instead of SQLite)

SECONDARY: Chrome Extension (companion)
├── Toolbar popup (quick view: "You have 7 active subscriptions, £142/mo")
├── Badge notification (price changes, upcoming renewals)
├── Opens web dashboard for full experience
└── Doesn't do background scanning — delegates to API
```

### 5.3 Migration Path from Current State

Current SG is already fairly well-positioned for this shift. The backend already does the heavy lifting (scanning + detection). The extension currently acts as a trigger + thin dashboard.

**Migration steps (estimated effort):**

| Step | Effort | Notes |
|------|--------|-------|
| 1. Build standalone web frontend | 2–4 weeks | Responsive landing + dashboard (reuse dashboard/ folder assets) |
| 2. Add OAuth web flow to backend | 1–2 weeks | Server-side Google OAuth with PKCE + refresh token storage |
| 3. Add cron-based scan scheduling | 1 week | Simple APScheduler or Celery beat for weekly scans |
| 4. Add notification system (email) | 1 week | Templates for weekly digest, renewal alerts |
| 5. Database upgrade (SQLite → PostgreSQL) | 1–2 weeks | Railway supports PostgreSQL natively; schema migration |
| 6. Convert extension to companion | 1 week | Strip background scanning; add popup that opens web dashboard |
| 7. CWS submission (optional) | 2–4 weeks | Submit companion extension for those who want toolbar quick-view |
| **Total** | **~9–15 weeks** | Parallelizable: frontend + OAuth + cron can happen simultaneously |

**Note:** Much of the existing code is reusable. The scan engine, detection logic, and data model stay the same. The primary change is **how** users authenticate and **where** triggers come from.

### 5.4 Time/Cost Tradeoffs

| Approach | Time to Launch | Development Cost | Maintenance Cost | User Reach |
|----------|---------------|------------------|------------------|------------|
| **Extension-only (current)** | 4–10 weeks (CWS review + OAuth verification) | Low-medium (mostly built) | Medium (CWS updates, MV3 workarounds) | ~50% UK + Chrome desktop only |
| **Web app-only (new)** | 6–12 weeks (full new frontend + OAuth + cron) | Medium-high | Low (no CWS gate, simpler architecture) | ~95% UK + all devices |
| **Both (recommended)** | 10–16 weeks (parallel tracks) | High one-time | Low-medium | ~95% UK + Chrome convenience |

**Key insight:** Extension-only saves a few weeks of development but **costs 50%+ of the potential user base** and creates a fundamentally unreliable scanning product. The web app investment pays for itself many times over.

### 5.5 Risk Assessment

| Risk | Extension-First | Web App-First | Mitigation |
|------|----------------|---------------|------------|
| **Google shuts down extension** | **Catastrophic** — product is the extension | **Low** — OAuth is independent, Gmail API isn't going away | Google has killed products before (Google+ API shutdown 2019). Extension is a thin layer over API; API-derived value survives. |
| **Google changes Gmail API** | **High** — same impact for both | **High** — same impact for both | Mitigation: abstract Gmail access behind an adapter layer. Monitor API deprecation notices. |
| **Google restricts sensitive OAuth scopes** | **High** — same impact for both | **High** — same impact for both | Could pivot to IMAP/OAuth if needed, but unlikely. Google needs Gmail API for Workspace apps. |
| **CWS rejects extension** | **High** — blocks launch entirely | **None** | Not a factor for web app. Extension is optional. |
| **OAuth verification takes 8+ weeks** | **High** — blocks CWS submission | **Low** — can launch "unverified" with testing users and limited scope | Web app can iterate with <100 users during verification. Extension cannot reach any users without CWS approval. |
| **New MV3 restrictions** | **High** — Google keeps tightening service worker capabilities | **None** | Google's direction is clear: less background processing, more user-triggered actions. Server-side scanning side-steps this entirely. |
| **Privacy controversy (data breach, bad press)** | **High** — extension carries extra stigma | **Moderate** — but easier to show security posture | Transparency + security audit + "no data sale" commitment. Same for both, but web app has better optics. |
| **Competitors (GhostSweep, Trackit, etc.)** | **High** — they have simpler onboarding | **Low** — now you match their onboarding | Web app levels the playing field. Extension adds proprietary friction. |

**Risk matrix verdict:** Web app first is **strictly lower risk** across every dimension except development timeline (slightly longer, but not risky).

### 5.6 Should SG Be Both? And Which First?

**Yes, both — but in the right order:**

1. **Phase 1 (MVP — 6–10 weeks):** Web app only
   - Build responsive web frontend
   - Server-side OAuth with refresh tokens
   - Cron-based weekly scanning
   - Email alerts (weekly digest, price changes, upcoming renewals)
   - Launch to early users

2. **Phase 2 (follow-up — 2–4 weeks after Phase 1):** Add companion Chrome extension
   - Build toolbar popup with subscription summary
   - Badge notifications for new detections
   - "Open full dashboard" link to web app
   - Submit to CWS (by now, OAuth verification is done from Phase 1)

3. **Phase 3 (optional — later):** Mobile apps / Workspace add-on
   - Mobile web is already covered by the responsive web app
   - Workspace add-on for Gmail inline experience (if demand exists)
   - PWA for mobile home-screen install without App Store

**Why Phase 1 = web app only:**
- Faster to validate product-market fit (no CWS gate)
- Works on all devices, all browsers
- Reliable scanning for all users
- If the product fails, you've learned with minimal sunk cost
- If it succeeds, you can add extension as a growth multiplier

**Extension commitment rationale (Phase 2):**
- The toolbar icon + badge is genuinely useful for "quick glance" use case
- Some users prefer extensions for habit-formation (it lives in their browser)
- It's a distribution channel (CWS search) — but treat it as discovery, not core product
- The extension should be **thin** — no scanning, no detection, just a pretty popup calling the API

---

## 6. Conclusion

**The Chrome extension is not the right primary delivery mechanism for Subscription Guardian.** Manifest V3's service worker constraints make reliable background Gmail scanning impossible. The CWS review gate adds unpredictable launch delays. The 50% UK Chrome market share caps addressable users. And the post-Unroll.me + post-spyware-scandal trust landscape actively works against browser extensions that request Gmail access.

**The web app is the right primary mechanism.** It delivers device-agnostic access, reliable server-side scanning with cron scheduling, zero friction onboarding, and a trust story that can be clearly communicated on the product's own site.

**Keep the extension as a companion** — not as the product. Build it once the web app is proven and OAuth verification is done.

**Current SG architecture is not wasted.** The FastAPI backend, detection engine, and scanning pipeline are fully reusable. The main work is: (1) building a quality web frontend, (2) adding server-side OAuth flow with refresh tokens, and (3) adding cron-based scheduling. Everything else stays.

---

## Appendix: Key Data Sources

1. StatCounter: Browser Market Share UK (Apr 2025–Apr 2026) — Chrome 50.94%
2. Google Gmail API Quota Documentation (May 2026) — 1.2M/minute/project, 6K/minute/user
3. Chrome Developers: Migrate to Service Worker — MV3 limitations
4. Deriv Tech: About Chrome Extension Service Workers — 30s idle timeout, 5min max duration
5. Reddit r/chrome_extensions: Review times (2024–2026) — 3 days to 3+ weeks
6. Google Groups OAuth Verification (Jan 2026) — 8+ week delays reported
7. The Guardian: Unroll.me "heartbroken" over data sales (2017)
8. Malwarebytes: Millions spied on by malicious browser extensions (July 2025)
9. Nylas: Google OAuth Verification Costs & Timelines — $540+ third-party assessment
10. GhostSweep product page — web app only, zero-storage claim
11. Trackit iOS app — Gmail scanning via mobile app, not extension
