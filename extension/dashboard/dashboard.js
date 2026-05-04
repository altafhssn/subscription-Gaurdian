// Full dashboard for Subscription Guardian
const BACKEND_URL = "http://localhost:8000";
let currentUserId = null;
let currentEmail = null;

document.addEventListener("DOMContentLoaded", async () => {
  const data = await getStorage();
  if (data.isLoggedIn && data.user_id) {
    currentUserId = data.user_id;
    currentEmail = data.email;
    document.getElementById("userEmail").textContent = data.email || "Connected";
    await loadFullDashboard();
  } else {
    document.getElementById("loadingState").innerHTML = `
      <div class="icon">🔐</div>
      <h2>Not connected</h2>
      <p>Open the Subscription Guardian popup to sign in.</p>
    `;
  }

  document.getElementById("scanBtn").addEventListener("click", triggerScan);
  document.getElementById("refreshBtn").addEventListener("click", loadFullDashboard);
});

function getStorage() {
  return new Promise((resolve) => chrome.storage.local.get(["user_id", "email", "isLoggedIn"], resolve));
}

async function loadFullDashboard() {
  document.getElementById("loadingState").style.display = "block";
  document.getElementById("dashboardContent").style.display = "none";

  chrome.runtime.sendMessage({ action: "getSubscriptions" }, async (subData) => {
    if (subData.error) {
      document.getElementById("loadingState").innerHTML = `
        <div class="icon">⚠️</div>
        <h2>Error</h2>
        <p>${subData.error}</p>
      `;
      return;
    }

    const subs = subData.subscriptions || [];

    if (subs.length === 0) {
      document.getElementById("loadingState").style.display = "none";
      document.getElementById("dashboardContent").style.display = "block";
      document.getElementById("emptyState").style.display = "block";
      document.getElementById("subTableBody").innerHTML = "";
      document.getElementById("subCount").textContent = "0";
      document.getElementById("statsGrid").innerHTML = `
        <div class="stat-card">
          <div class="label">Monthly Spend</div>
          <div class="value" style="color:var(--text-dim)">—</div>
        </div>
        <div class="stat-card">
          <div class="label">Subscriptions</div>
          <div class="value" style="color:var(--text-dim)">0</div>
        </div>
      `;
      document.getElementById("gapHero").style.display = "none";
      document.getElementById("categoryGrid").innerHTML = "";
      return;
    }

    const stats = await new Promise((r) => chrome.runtime.sendMessage({ action: "getStats" }, r));

    document.getElementById("loadingState").style.display = "none";
    document.getElementById("dashboardContent").style.display = "block";
    document.getElementById("emptyState").style.display = "none";

    // Stats grid
    document.getElementById("statsGrid").innerHTML = `
      <div class="stat-card">
        <div class="label">Monthly Spend</div>
        <div class="value" style="color:var(--red)">₹${(stats.total_monthly_spend || 0).toLocaleString()}</div>
        <div class="sub">₹${((stats.total_monthly_spend || 0) * 12).toLocaleString()}/year</div>
      </div>
      <div class="stat-card">
        <div class="label">Total Subscriptions</div>
        <div class="value" style="color:var(--orange)">${subs.length}</div>
        <div class="sub">${stats.is_confirmed || 0} confirmed</div>
      </div>
      <div class="stat-card">
        <div class="label">Estimated Perceived</div>
        <div class="value">₹500</div>
        <div class="sub">What most users think</div>
      </div>
      <div class="stat-card">
        <div class="label">Gap</div>
        <div class="value" style="color:${stats.surprise_gap > 0 ? 'var(--green)' : 'var(--text-dim)'}">
          ${stats.surprise_gap > 0 ? '+' : ''}${(stats.surprise_gap_pct || 0)}%
        </div>
        <div class="sub">What you're missing</div>
      </div>
    `;

    // Gap hero
    const gap = stats.surprise_gap || 0;
    document.getElementById("gapValue").textContent = `₹${(gap * 12).toLocaleString()}`;
    document.getElementById("gapHero").style.display = gap > 0 ? "block" : "none";

    // Category grid
    const byCategory = stats.by_category || {};
    document.getElementById("categoryGrid").innerHTML = Object.entries(byCategory).map(([cat, amt]) => `
      <div class="cat-card">
        <div class="cat-name">${cat}</div>
        <div class="cat-amount" style="color:var(--orange)">₹${amt.toLocaleString()}</div>
      </div>
    `).join("");

    // Subscription table
    document.getElementById("subCount").textContent = subs.length;
    document.getElementById("subTableBody").innerHTML = subs.map((sub) => {
      const amountStr = sub.amount ? `₹${sub.amount.toLocaleString()}` : "—";
      const freqLabel = sub.frequency || "monthly";
      const statusClass = sub.is_confirmed ? "confirmed" : "unconfirmed";
      const statusText = sub.is_confirmed ? "✅ Confirmed" : "⚠️ Unconfirmed";

      return `
        <tr>
          <td><strong>${sub.name}</strong></td>
          <td>${sub.category || "Other"}</td>
          <td class="amount">${amountStr}</td>
          <td>${freqLabel}</td>
          <td><span class="status-badge ${statusClass}">${statusText}</span></td>
          <td>
            <button class="btn btn-sm ${sub.is_confirmed ? 'btn-danger' : 'btn-secondary'}" 
                    data-sub-id="${sub.id}"
                    data-action="${sub.is_confirmed ? 'delete' : 'confirm'}">
              ${sub.is_confirmed ? '🗑️' : '✓'} ${sub.is_confirmed ? 'Delete' : 'Confirm'}
            </button>
          </td>
        </tr>
      `;
    }).join("");

    // Table action handlers
    document.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const subId = btn.dataset.subId;
        const action = btn.dataset.action;

        if (action === "confirm") {
          chrome.runtime.sendMessage({ action: "confirmSubscription", sub_id: subId, updates: {} }, loadFullDashboard);
        } else if (action === "delete") {
          chrome.runtime.sendMessage({ action: "deleteSubscription", sub_id: subId }, loadFullDashboard);
        }
      });
    });
  });
}

async function triggerScan() {
  document.getElementById("loadingState").style.display = "block";
  document.getElementById("loadingState").innerHTML = `
    <div class="icon"><span style="display:inline-block;width:48px;height:48px;border:4px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin 0.8s linear infinite;"></span></div>
    <h2>Scanning inbox...</h2>
    <p>This may take 30-60 seconds.</p>
  `;
  document.getElementById("dashboardContent").style.display = "none";

  chrome.runtime.sendMessage({ action: "scan" }, async () => {
    await new Promise((r) => setTimeout(r, 2000));
    await loadFullDashboard();
  });
}
