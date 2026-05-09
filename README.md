# Subscription Guardian — Backend

Track forgotten subscriptions from your Gmail inbox.

FastAPI + SQLite. Deploy-ready for Railway.

## Quick Start
```bash
cd backend
pip install -r requirements.txt
python main.py
```

## Env Vars
| Variable | Description |
|---|---|
| GOOGLE_CLIENT_ID | Google OAuth client ID |
| GOOGLE_CLIENT_SECRET | Google OAuth client secret |
| BACKEND_URL | Deployed URL (e.g. https://subguard.up.railway.app) |
| APP_SECRET | App encryption secret |
| SESSION_SECRET | Session encryption secret |

## Deploy
Set Railway Root Directory to `backend/`.
# deploy trigger Saturday 09 May 2026 11:06:36 AM IST
