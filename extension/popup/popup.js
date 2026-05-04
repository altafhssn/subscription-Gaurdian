// Popup script for Subscription Guardian
const BACKEND_URL = "http://localhost:8000";

// DOM refs
const states = {
  loggedOut: document.getElementById("stateLoggedOut"),
  loading: document.getElementById("stateLoading"),
  dashboard: document.getElementById("stateDashboard"),
  empty: document.getElementById("stateEmpty"),
  error: document.getElementById("stateError"),
};

function showState(name) {
  Object.values(states).forEach((s) => s.classList.remove("active"));
  states[name].classList.add("active");
}

function updateBadge(text, color) {
  const badge = document.getElementById("statusBadge");
  badge.textContent = text;
  badge.style.background = color || "#6C5CE7";
}

// ── Check auth on load ──────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  chrome.storage.local.get(["user_id", "email", "isLoggedIn"], async (data) => {
    if (data.isLoggedIn && data.user_id) {
      document.getElementById("userEmail").textContent = data.email || "Connected";
      updateBadge("Connected", "#00D68F");
      await loadDashboard(data.user_id);
    } else {
      // Check URL params (OAuth callback may have set them)
      // This happens on first login
      showState("loggedOut");
      updateBadge("Not connected");
    }
  });

  // Check if OAuth returned params (auth/success page sets storage)
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const url = tabs[0]?.url || "";
    const params = new URLSearchParams(url.split("?")[1] || "");
    const userId = params.get("user_id");
    const email = params.get("email");
    
    if (userId && email) {
      chrome.storage.local.set({ isLoggedIn: true, user_id: userId, email });
      document.getElementById("userEmail").textContent = email;
      updateBadge("Connected", "#00D68F");
      showState("loading");
      document.getElementById("loadingTitle").textContent = "Scanning your inbox...";
      loadDashboard(userId);
    }
  });
});

// ── Login button ───────────────────────────────────────

document.getElementById("loginBtn").addEventListener("click", () => {
  chrome.runtime.sendMessage({ action: "login" });
  showState("loading");
  document.getElementById("loadingTitle").textContent = "Opening Google login...";
  document.getElementById("loadingDesc").textContent = "Complete the sign-in in the new tab.";
});

// ── Logout ──────────────────────────────────────────────

document.getElementById("logoutLink").addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.sendMessage({ action: "logout" }, () => {
    showState("loggedOut");
    updateBadge("Not connected");
    document.getElementById("userEmail").textContent = "Not connected";
  });
});

// ── Load Dashboard ─────────────────────────────────────

async function loadDashboard(userId) {
  showState("loading");
  document.getElementById("loadingTitle").textContent = "Loading your subscriptions...";

  // First check if we have cached subs
  chrome.runtime.sendMessage({ action: "getSubscriptions" }, async (subData) => {
    if (subData.error) {
      showState("error");
      document.getElementById("errorDesc").textContent = subData.error;
      return;
    }

    const subs = subData.subscriptions || [];
    
    if (subs.length === 0) {
      // No cached subs, trigger a scan
      await triggerScan(userId);
      return;
    }

    // Load stats + display
    displaySubscriptions(subs, userId);
    await loadStats(userId);
  });
}

async function triggerScan(userId) {
  showState("loading");
  document.getElementById("loadingTitle").textContent = "Scanning your inbox...";
  document.getElementById("loadingDesc").textContent = "Checking your 90 days of email history.";

  chrome.runtime.sendMessage({ action: "scan" }, async (scanData) => {
    if (scanData.error) {
      showState("error");
      document.getElementById("errorDesc").textContent = scanData.error;
      return;
    }

    if (scanData.subscriptions_found === 0 && (!scanData.subscriptions || scanData.subscriptions.length === 0)) {
      showState("empty");
      return;
    }

    // Load fresh data
    chrome.runtime.sendMessage({ action: "getSubscriptions" }, (subData) => {
      const subs = subData.subscriptions || [];
      if (subs.length === 0) {
        showState("empty");
        return;
      }
      displaySubscriptions(subs, userId);
      loadStats(userId);
    });
  });
}

function displaySubscriptions(subs, userId) {
  showState("dashboard");

  const list = document.getElementById("subList");
  list.innerHTML = "";

  document.getElementById("activeSubs").textContent = subs.length;

  subs.forEach((sub) => {
    const item = document.createElement("div");
    item.className = "sub-item";
    if (!sub.is_confirmed) item.classList.add("unconfirmed");

    const freqLabel = sub.frequency === "yearly" ? "/yr" : sub.frequency === "quarterly" ? "/qr" : "/mo";
    const amountStr = sub.amount ? `₹${sub.amount.toLocaleString()}` : "—";

    item.innerHTML = `
      <div class="sub-info">
        <div class="sub-name">${sub.name}</div>
        <div class="sub-meta">
          ${sub.category} · ${sub.frequency || "monthly"}
          ${!sub.is_confirmed ? '· <span style="color:#FFA726">Unconfirmed</span>' : ""}
        </div>
      </div>
      <div class="sub-amount">${amountStr}${amountStr !== "—" ? freqLabel : ""}</div>
    `;

    // Click to confirm/edit
    item.addEventListener("click", () => {
      if (!sub.is_confirmed) {
        chrome.runtime.sendMessage(
          { action: "confirmSubscription", sub_id: sub.id, updates: {} },
          () => loadDashboard(userId)
        );
      }
    });

    list.appendChild(item);
  });
}

async function loadStats(userId) {
  chrome.runtime.sendMessage({ action: "getStats" }, (stats) => {
    if (stats.error) return;

    document.getElementById("monthlySpend").textContent = `₹${(stats.total_monthly_spend || 0).toLocaleString()}`;

    const gap = stats.surprise_gap || 0;
    const gapEl = document.getElementById("gapText");
    gapEl.textContent = `₹${(gap * 12).toLocaleString()}/yr`;
    
    if (gap > 0) {
      document.getElementById("gapBanner").style.display = "block";
    } else {
      document.getElementById("gapBanner").style.display = "none";
    }
  });
}

// ── Rescan buttons ─────────────────────────────────────

document.getElementById("rescanBtn").addEventListener("click", async () => {
  const data = await new Promise((r) => chrome.storage.local.get(["user_id"], r));
  if (data.user_id) triggerScan(data.user_id);
});

document.getElementById("rescanEmptyBtn").addEventListener("click", async () => {
  const data = await new Promise((r) => chrome.storage.local.get(["user_id"], r));
  if (data.user_id) triggerScan(data.user_id);
});

// ── Open full dashboard ────────────────────────────────

document.getElementById("openDashboardBtn").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

// ── Retry ───────────────────────────────────────────────

document.getElementById("retryBtn").addEventListener("click", async () => {
  const data = await new Promise((r) => chrome.storage.local.get(["user_id"], r));
  if (data.user_id) loadDashboard(data.user_id);
  else showState("loggedOut");
});
