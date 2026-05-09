// main.js — Subscription Guardian landing page
// Security: all user-displayed values use textContent / DOM API, never innerHTML.

(function () {
  'use strict';

  // ── Year in footer ──────────────────────────────────
  const yr = document.getElementById('yr');
  if (yr) yr.textContent = String(new Date().getFullYear());

  // ── Mobile nav ──────────────────────────────────────
  const navToggle = document.getElementById('navToggle');
  const navLinks  = document.getElementById('navLinks');
  if (navToggle && navLinks) {
    navToggle.addEventListener('click', function () {
      const open = navLinks.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    // Close menu when any link is clicked
    navLinks.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        navLinks.classList.remove('open');
        navToggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // ── Calculator ──────────────────────────────────────
  // GBP-formatted output, all via textContent. Formula is documented:
  // We assume an average of ~30% of subscriptions are "forgotten" overpayment.
  // (Citizens Advice 2024: UK adults overpay an average of £295/yr on subs.)
  const subs    = document.getElementById('cSubs');
  const avg     = document.getElementById('cAvg');
  const months  = document.getElementById('cMonths');
  const subsOut = document.getElementById('cSubsOut');
  const avgOut  = document.getElementById('cAvgOut');
  const mthOut  = document.getElementById('cMonthsOut');
  const result  = document.getElementById('cResult');
  const detail  = document.getElementById('cDetail');

  const gbp = new Intl.NumberFormat('en-GB', {
    style: 'currency', currency: 'GBP', maximumFractionDigits: 0
  });

  function clamp(value, min, max) {
    const n = Number(value);
    if (!Number.isFinite(n)) return min;
    return Math.min(Math.max(n, min), max);
  }

  function updateCalc() {
    if (!subs || !avg || !months) return;

    const s = clamp(subs.value, 2, 20);
    const a = clamp(avg.value, 3, 50);
    const m = clamp(months.value, 1, 24);

    // Total monthly spend × estimated waste rate (30%) × months
    const wasteMonthly = s * a * 0.30;
    const wasteTotal   = Math.round(wasteMonthly * m);

    // textContent only — never innerHTML
    subsOut.textContent = String(s);
    avgOut.textContent  = gbp.format(a);
    mthOut.textContent  = String(m);
    result.textContent  = gbp.format(wasteTotal);

    // Build detail text via DOM API (avoids any innerHTML risk)
    const totalMonthly = gbp.format(s * a);
    const wasteFmt     = gbp.format(Math.round(wasteMonthly));
    detail.textContent =
      `${totalMonthly}/mo total · ~${wasteFmt}/mo likely unused · over ${m} months`;

    // Update aria-valuenow for accessibility
    subs.setAttribute('aria-valuenow', String(s));
    avg.setAttribute('aria-valuenow', String(a));
    months.setAttribute('aria-valuenow', String(m));
  }

  if (subs && avg && months) {
    [subs, avg, months].forEach(function (el) {
      el.addEventListener('input', updateCalc);
    });
    updateCalc();
  }

  // ── Pricing toggle (monthly ↔ annual) ──────────────
  const ptMonthly  = document.getElementById('ptMonthly');
  const ptAnnual   = document.getElementById('ptAnnual');
  const planAmount = document.getElementById('planAmount');
  const planPeriod = document.getElementById('planPeriod');
  const planTag    = document.getElementById('planTag');

  function setMonthly() {
    if (!ptMonthly || !ptAnnual) return;
    ptMonthly.classList.add('active');
    ptAnnual.classList.remove('active');
    ptMonthly.setAttribute('aria-selected', 'true');
    ptAnnual.setAttribute('aria-selected', 'false');
    if (planAmount) planAmount.textContent = '3';
    if (planPeriod) planPeriod.textContent = '/month';
    if (planTag)    planTag.textContent    = 'Cancel anytime';
  }

  function setAnnual() {
    if (!ptMonthly || !ptAnnual) return;
    ptAnnual.classList.add('active');
    ptMonthly.classList.remove('active');
    ptAnnual.setAttribute('aria-selected', 'true');
    ptMonthly.setAttribute('aria-selected', 'false');
    if (planAmount) planAmount.textContent = '25';
    if (planPeriod) planPeriod.textContent = '/year';
    if (planTag)    planTag.textContent    = '£25/yr — save £11 vs monthly';
  }

  if (ptMonthly) ptMonthly.addEventListener('click', setMonthly);
  if (ptAnnual)  ptAnnual.addEventListener('click', setAnnual);
})();
