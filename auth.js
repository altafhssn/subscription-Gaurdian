// auth.js — Subscription Guardian sign-in / waitlist page
// Security:
//  - No password collection (Google OAuth is the only auth path)
//  - No localStorage fallback (we tell the user honestly if it fails)
//  - Honeypot field to catch bots
//  - All user data rendered via textContent

(function () {
  'use strict';

  const form    = document.getElementById('waitlistForm');
  const emailEl = document.getElementById('waitEmail');
  const errEl   = document.getElementById('waitEmailErr');
  const btn     = document.getElementById('waitBtn');
  const hp      = document.getElementById('hp_field');
  const toast   = document.getElementById('toast');

  // Toast helper — textContent only, type validated against allow-list
  function showToast(message, type) {
    if (!toast) return;
    toast.textContent = String(message);
    const validTypes = ['success', 'error', ''];
    const cls = validTypes.indexOf(type) >= 0 ? type : '';
    toast.className = 'toast show' + (cls ? ' ' + cls : '');
    setTimeout(function () { toast.classList.remove('show'); }, 4500);
  }

  // RFC-5321 isn't fun to implement; this catches the obvious garbage
  function isValidEmail(s) {
    if (!s || s.length > 254) return false;
    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s);
  }

  function setError(msg) {
    if (errEl) errEl.textContent = msg || '';
    if (emailEl) {
      emailEl.setAttribute('aria-invalid', msg ? 'true' : 'false');
    }
  }

  if (!form) return;

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    setError('');

    const email = (emailEl.value || '').trim();

    // Validate
    if (!email) {
      setError('Please enter your email address.');
      emailEl.focus();
      return;
    }
    if (!isValidEmail(email)) {
      setError('That email doesn\'t look right — try again?');
      emailEl.focus();
      return;
    }

    // Honeypot — if filled, silently "succeed" (bot will think it worked)
    if (hp && hp.value) {
      // Don't tell the bot we caught it; just pretend success
      showToast('You\'re on the list!', 'success');
      form.reset();
      return;
    }

    // Disable while submitting
    btn.disabled    = true;
    btn.textContent = 'Adding you...';

    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, hp_check: '' }),
      });

      if (res.status === 429) {
        showToast('Too many requests — please wait a minute and try again.', 'error');
        return;
      }
      if (res.status === 409) {
        // Already on the list — friendly message
        showToast('You\'re already on the list — we\'ll be in touch soon.', '');
        form.reset();
        return;
      }
      if (!res.ok) {
        // Server error — be honest
        showToast('Something went wrong — please try again, or email us directly.', 'error');
        return;
      }

      // Success
      showToast('You\'re on the list! Check your inbox for a confirmation.', 'success');
      form.reset();

    } catch (err) {
      // Network/offline — be honest, don't pretend
      showToast('Couldn\'t reach our servers — please try again in a moment.', 'error');
    } finally {
      btn.disabled    = false;
      btn.textContent = 'Join the waitlist';
    }
  });

  // Clear error as user types
  if (emailEl) {
    emailEl.addEventListener('input', function () {
      if (errEl && errEl.textContent) setError('');
    });
  }
})();
