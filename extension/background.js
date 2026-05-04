// Background service worker for Subscription Guardian
const BACKEND_URL = "http://localhost:8000";

// Handle extension installation
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    chrome.storage.local.set({
      isLoggedIn: false,
      user_id: null,
      email: null,
    });
    chrome.tabs.create({ url: "https://console.cloud.google.com/apis/credentials" });
  }
});

// Listen for messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Background received:", message);

  switch (message.action) {
    case "login":
      handleLogin(sendResponse);
      return true; // Keep channel open for async

    case "checkAuth":
      chrome.storage.local.get(["user_id", "email", "isLoggedIn"], (data) => {
        sendResponse(data);
      });
      return true;

    case "scan":
      chrome.storage.local.get(["user_id"], (data) => {
        if (!data.user_id) {
          sendResponse({ error: "Not logged in" });
          return;
        }
        handleScan(data.user_id, sendResponse);
      });
      return true;

    case "getSubscriptions":
      chrome.storage.local.get(["user_id"], (data) => {
        if (!data.user_id) {
          sendResponse({ error: "Not logged in" });
          return;
        }
        getSubscriptions(data.user_id, sendResponse);
      });
      return true;

    case "getStats":
      chrome.storage.local.get(["user_id"], (data) => {
        if (!data.user_id) {
          sendResponse({ error: "Not logged in" });
          return;
        }
        getStats(data.user_id, sendResponse);
      });
      return true;

    case "confirmSubscription":
      confirmSubscription(message.sub_id, message.updates, sendResponse);
      return true;

    case "deleteSubscription":
      deleteSubscription(message.sub_id, sendResponse);
      return true;

    case "logout":
      chrome.storage.local.set({ isLoggedIn: false, user_id: null, email: null }, () => {
        sendResponse({ status: "logged_out" });
      });
      return true;
  }
});

async function handleLogin(sendResponse) {
  const loginUrl = `${BACKEND_URL}/auth/login`;
  // Open login in a new tab
  chrome.tabs.create({ url: loginUrl });
  sendResponse({ status: "opening_login_tab" });
}

async function handleScan(userId, sendResponse) {
  try {
    const resp = await fetch(`${BACKEND_URL}/api/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
    const data = await resp.json();
    sendResponse(data);
  } catch (err) {
    sendResponse({ error: err.message });
  }
}

async function getSubscriptions(userId, sendResponse) {
  try {
    const resp = await fetch(`${BACKEND_URL}/api/subscriptions/${userId}`);
    const data = await resp.json();
    sendResponse(data);
  } catch (err) {
    sendResponse({ error: err.message });
  }
}

async function getStats(userId, sendResponse) {
  try {
    const resp = await fetch(`${BACKEND_URL}/api/stats/${userId}`);
    const data = await resp.json();
    sendResponse(data);
  } catch (err) {
    sendResponse({ error: err.message });
  }
}

async function confirmSubscription(subId, updates, sendResponse) {
  try {
    const resp = await fetch(`${BACKEND_URL}/api/subscriptions/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sub_id: subId, ...updates }),
    });
    const data = await resp.json();
    sendResponse(data);
  } catch (err) {
    sendResponse({ error: err.message });
  }
}

async function deleteSubscription(subId, sendResponse) {
  try {
    const resp = await fetch(`${BACKEND_URL}/api/subscriptions/${subId}`, {
      method: "DELETE",
    });
    const data = await resp.json();
    sendResponse(data);
  } catch (err) {
    sendResponse({ error: err.message });
  }
}
