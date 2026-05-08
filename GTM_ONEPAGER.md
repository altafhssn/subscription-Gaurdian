# Subscription Guardian — GTM One-Pager

## The Core Idea
AI subscription tracker that scans your Gmail and shows you the **2.5x gap** between what you *think* you spend vs. what you *actually* spend on subscriptions. UK-first, product-led growth.

**Elevator pitch:** *"Rocket Money for the UK — but instead of linking your bank, it reads your Gmail receipts in 30 seconds."*

---

## Product Flow (The Funnel)

| Step | User Action | What Happens |
|------|------------|--------------|
| 1 | Visit landing page | See "Find £100s in forgotten subscriptions" |
| 2 | Click "Connect Gmail — Free" | Google OAuth (read-only) |
| 3 | Scan runs (30-60s) | Backend searches emails, detects services, extracts amounts |
| 4 | **Surprise reveal** | "You think you spend £68/mo. You actually spend £175/mo. Here's where." |
| 5 | Free dashboard | Last 5 services + "Unlock unlimited scans for £3.99/mo" |
| 6 | Premium upsell | Monthly auto-scan, price hike alerts, cancel links |

**Conversion event = Step 4.** The surprise gap IS the marketing. Shareable screenshot is built-in virality.

---

## Target Customer

| Attribute | Detail |
|-----------|--------|
| Geography | UK (sole trader, India ops) |
| Persona | 25-45, urban, 3+ active subscriptions (Netflix, Spotify, gym, cloud storage, meal kits) |
| Pain | "I have no idea what I'm paying each month" — proven 2.5x perception gap |
| Behavior | Likes Reddit (r/UKPersonalFinance), checks deals, uses Revolut/Monzo |
| Trigger | Post-holiday spending guilt, annual Netflix price hike, "where's my money going?" moment |

---

## Acquisition Channels

### Phase 1: Zero-Spend Organic (Months 1-3)
| Channel | Tactic | Expected Traffic |
|---------|--------|-----------------|
| **Reddit** 🔥 | Post scan results in r/UKPersonalFinance, r/CasualUK, r/Frugal. "I scanned my Gmail and found £200/mo I forgot about." | 10K-50K views per post |
| **Hacker News** | Launch with the surprise gap stat + open source teaser | 5K-20K visits |
| **Product Hunt** | Launch with "Find your forgotten subscriptions" hook | 2K-10K visits |
| **TikTok/Reels** | 30s demo: "Watch me find £147/mo in 30 seconds" | Viral potential |
| **Twitter/X** | Thread: "6 subscriptions you're paying for but forgot about" | 1K-5K visits |

**Conversion math (organic):** 10,000 visitors → 15-25% OAuth click = 1,500-2,500 signups → 5-8% premium = **75-200 paying users** in month one at zero cost.

### Phase 2: Paid (Month 4+, after validation)
| Channel | Keyword/TA | Est. CPC | Budget |
|---------|-----------|----------|--------|
| Google Ads | "track subscriptions UK", "find forgotten payments", "subscription manager" | £0.50-£1.50 | £500-1,000/mo |
| Reddit Ads | r/UKPersonalFinance, r/UK, r/Frugal audiences | £0.30-£0.80 | £200-500/mo |
| Meta | Lookalike from OAuth signups (once we have 500+) | £0.40-£1.00 | £300-500/mo |

---

## Pricing Model

| Tier | Price | Features |
|------|-------|----------|
| **Free** | £0 | One-time scan, up to 10 subs, basic dashboard |
| **Guardian** | £3.99/mo | Monthly auto-scan, unlimited subs, price hike alerts, cancel links |
| *(Annual)* | £39.99/yr (£3.33/mo) | Same as monthly, 16% discount |

**Psychological pricing:** £3.99 = "coffee price." Easy mental justification when you just found £100+ in savings.

---

## Revenue Scenarios (Year 1)

### Conservative — Slow organic, no virality
- Monthly visitors: 500 → 2,000 by month 12
- Signups: 75 → 400 cumulative
- Premium conversion: 4%
- MRR: **£12 → £64/mo** by month 12
- Annual revenue: **~£380**

### Moderate — One Reddit/HN post hits
- Monthly visitors: 2,000 → 8,000
- Signups: 300 → 1,600 cumulative
- Premium conversion: 6%
- MRR: **£72 → £384/mo**
- Annual revenue: **~£2,300**

### Aggressive — Viral surprise gap share
- Monthly visitors: 5,000 → 25,000
- Signups: 750 → 5,000 cumulative
- Premium conversion: 8%
- MRR: **£240 → £1,600/mo**
- Annual revenue: **~£8,600**

---

## Cost Structure

| Item | Monthly Fixed | Variable (per user) |
|------|-------------|-------------------|
| Railway hosting | £5-20 (scales with DB) | — |
| PostgreSQL (Railway) | £0 (free tier, 500MB) | £7/5GB after |
| Google Cloud (Gmail API) | £0 (<10K requests/day) | £0.50/1K requests |
| Domain + email | £10-15/yr | — |
| Stripe fees | — | 1.5% + £0.20/tx |
| Google OAuth verification fee | £0 (one-time, needed at 100 users) | ~$100-500 |
| Total | **£5-20/mo** at small scale | ~£0.26/user at £3.99 tier |

**Burn rate:** ~£15/mo at launch. Profitable from literally 5 premium users.

---

## Key Metrics Dashboard

| Metric | Target | Why |
|--------|--------|-----|
| Landing → OAuth click | 15-25% | Need strong hook |
| OAuth → scan complete | 80%+ | Tech must not break |
| Free → Premium conversion | 5-10% | Industry standard for utility |
| Monthly churn (premium) | <8% | Fintech avg is 5-8% |
| Months to recover CAC | <3 | Easy at £0 CAC organically |
| NPS | 40+ | Must be delightful, not creepy |
| GDPR complaint rate | <0.1% | Trust is the moat |

---

## Launch Timeline

| Week | Action | Cost |
|------|--------|------|
| **Pre-launch** | Finalize landing copy, test OAuth flow with 5 beta users | £0 |
| **Week 1** | Ship to r/UKPersonalFinance + Hacker News. Post the surprise gap stat. | £0 |
| **Week 2** | Product Hunt launch with beta. Collect testimonials. | £0 |
| **Week 3** | 1st premium users. Fix onboarding leaks. | £0 |
| **Week 4** | Retro. Decide: double down organic or start paid. | £0 |
| **Month 2-3** | Iterate on discovery data. Add cancel links. Reddit AMA. | £0-200 |
| **Month 4** | If PMF confirmed: launch Google Ads at £500/mo | £500/mo |
| **Month 6** | Decision: keep indie or raise/sell | — |

---

## Risk Factors

1. **Google OAuth verification** — Must apply at 100 users. App can be rejected if "psychologically manipulative" (scary spending stats). Mitigation: frame as empowering, not shaming.
2. **Gmail API quota** — 250K requests/day/user is generous, but each scan fetches 50+ messages. Fine for <1K daily active users.
3. **GDPR / ICO** — Must register as data processor. Token encryption (AES-256-GCM) + 90-day auto-delete + delete endpoint. Cost: £0 (self-service) to £40 (ICO registration fee).
4. **Spam classification** — OAuth emails sometimes land in spam. Mitigation: pre-send a test email, ask user to whitelist.
5. **Trust barrier** — "Read my Gmail??" Solution: open-source backend, publish security white paper, independent audit.

---

## One-Line Strategy

> **Build the surprise, sell the control. Free scan shows the problem. £3.99/mo sells the solution. Zero burn until validation.**

---

*Vegapunk is analysing budget/revenue numbers in detail — results landing here: [`VEGAPUNK_GTM_ANALYSIS.md`](VEGAPUNK_GTM_ANALYSIS.md)*
