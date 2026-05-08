// success.js — post-OAuth landing page
// M3: ALL user data rendered via textContent, never innerHTML
// H1: no PII from URL params; identity fetched from /api/me (session cookie)
// C2: relies on session cookie set by /auth/callback

(async function () {
  const emailEl   = document.getElementById('email');
  const scanBtn   = document.getElementById('scanBtn');
  const statusEl  = document.getElementById('status');
  const resultsEl = document.getElementById('results');
  const subListEl = document.getElementById('subList');

  // Fetch identity from session — no URL params needed
  try {
    const meResp = await fetch('/api/me', { credentials: 'include' });
    if (!meResp.ok) {
      window.location.href = '/auth/login';
      return;
    }
    const me = await meResp.json();
    emailEl.textContent = me.email || 'your account';
  } catch (_) {
    statusEl.textContent = 'Could not verify session.';
  }

  scanBtn.addEventListener('click', startScan);

  async function startScan() {
    scanBtn.disabled     = true;
    scanBtn.textContent  = 'Scanning...';
    statusEl.textContent = 'Scanning your inbox for subscription emails...';

    try {
      const resp = await fetch('/api/scan', { credentials: 'include' });
      if (resp.status === 401) {
        statusEl.textContent = 'Session expired. Redirecting to login...';
        setTimeout(() => { window.location.href = '/auth/login'; }, 1500);
        return;
      }
      const data = await resp.json();

      if (data.error) {
        statusEl.textContent = 'Error: ' + data.error;
        scanBtn.disabled = false;
        scanBtn.textContent = 'Try Again';
        return;
      }

      // Set stats — all textContent (M3)
      document.getElementById('subCount').textContent     = String(data.total_subs || 0);
      document.getElementById('monthlySpend').textContent = '\u20B9' + (data.total_monthly_spend || 0).toLocaleString();
      document.getElementById('yearlySpend').textContent  = '\u20B9' + (data.total_yearly_spend  || 0).toLocaleString();
      document.getElementById('perceived').textContent    = '\u20B9' + (data.estimated_perceived_spend || 500) + '/mo';
      document.getElementById('surpriseGap').textContent  = '\u20B9' + (data.surprise_gap || 0).toLocaleString() + '/mo';
      resultsEl.style.display = 'block';
      subListEl.textContent   = '';

      (data.subscriptions || []).forEach(function(sub) {
        var div = document.createElement('div');
        div.className = 'sub-item';

        var left    = document.createElement('div');
        var nameDiv = document.createElement('div');
        var freqDiv = document.createElement('div');
        nameDiv.className   = 'sub-name';
        freqDiv.className   = 'sub-freq';
        nameDiv.textContent = sub.name || 'Unknown';
        freqDiv.textContent = (sub.frequency || 'monthly') + ' \u00B7 ' + (sub.category || 'Other');
        left.appendChild(nameDiv);
        left.appendChild(freqDiv);

        var right   = document.createElement('div');
        var amtDiv  = document.createElement('div');
        var perDiv  = document.createElement('div');
        amtDiv.className    = 'sub-amount';
        perDiv.className    = 'sub-freq';
        amtDiv.textContent  = sub.amount ? '\u20B9' + sub.amount.toLocaleString() : '\u2014';
        perDiv.textContent  = '/mo';
        right.appendChild(amtDiv);
        right.appendChild(perDiv);

        div.appendChild(left);
        div.appendChild(right);
        subListEl.appendChild(div);
      });

      statusEl.textContent = 'Scan complete! Found ' + (data.total_subs || 0) + ' subscriptions.';
      scanBtn.textContent  = 'Scan Again';
      scanBtn.disabled     = false;

    } catch (err) {
      statusEl.textContent = 'Error: ' + err.message;
      scanBtn.textContent  = 'Try Again';
      scanBtn.disabled     = false;
    }
  }
})();
