# Subscription Guardian

Find forgotten subscriptions in your Gmail. Track actual spend vs. what you think you're spending.

## Quick Start

### 1. Backend
```bash
cd backend
cp ../.env.example .env
pip install -r requirements.txt
python main.py
```

### 2. Load Extension
1. Open Chrome → `chrome://extensions`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked" → select `extension/`
4. Pin the extension icon

### 3. Connect Gmail
1. Click the extension icon → "Connect Gmail"
2. Complete OAuth in the new tab
3. Wait for scan to complete

### 4. Deploy (Optional)
```bash
# Railway
cd deploy
railway login
railway up
```

## Tech Stack
- **Backend:** FastAPI + SQLite + Gmail API
- **Extension:** Manifest V3 Chrome Extension
- **Deploy:** Docker / Railway / VPS

## Files
```
subscription-guardian/
├── backend/
│   ├── main.py          # FastAPI server + detection engine
│   └── requirements.txt
├── extension/
│   ├── manifest.json    # Chrome extension config
│   ├── background.js    # Service worker
│   ├── popup/           # Extension popup UI
│   ├── dashboard/       # Full dashboard (options page)
│   └── icons/
├── deploy/
│   ├── Dockerfile
│   └── railway.toml
└── .env.example
```
