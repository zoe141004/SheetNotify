# 🔔 SheetNotify

SheetNotify is a simple automation platform: **whenever new data is entered into a registered user's Google Sheet, the user gets an instant Telegram message** describing exactly what changed. Every notification is also stored in a database as a log (what changed + when it was sent).

> Anyone can sign up, connect a Google Sheet, link Telegram, and start receiving alerts — no manual scripting required.

---

## ✨ What it does (core flow)

1. **Login** — the user signs in with their Google account.
2. **Authorize Google Sheets** — OAuth grants read access to the user's spreadsheets.
3. **Pick a sheet** — the user selects the spreadsheet/tab to watch.
4. **Detect changes** — the platform watches the sheet and detects when new data is added (and edits/deletes).
5. **Notify Telegram** — a message is sent to the user's linked Telegram with the exact change.
6. **Log everything** — each notification is saved to the database: the change, and the date/time it was sent.

---

## 🧠 How change detection works

The platform stores a **snapshot** of each watched sheet in PostgreSQL. On every check it pulls the current sheet data and **diffs it against the stored snapshot**, then reports changes at the right granularity:

| Change | Example Telegram line |
|--------|-----------------------|
| New row added | `➕ Row #5: Name=John, Email=john@x.com` |
| Many rows added | `➕ Added 1000 rows (#16–#1015)` |
| Single cell edited | `✏️ B3 (Age): "40" → "41"` |
| Empty cell filled | `✏️ A5 (Name): added "abc"` |
| Whole column range | `✏️ C2:C9 (City): 8 cells updated` |
| Block / rectangle | `✏️ A2:C4 updated (9 cells)` |
| Column added / removed | `➕ Added column D (Status)` / `🗑️ Deleted column C (City)` |
| Row deleted | `🗑️ Deleted row #15 (...)` |

**Noise is filtered out:** `null → ""`, whitespace-only edits, and fully-blank added rows are ignored. **All changes from one detection cycle are delivered in a single Telegram message** (never one message per row).

### Triggers (all feed the same diff engine)
- **Polling** (default, zero-setup): a background worker re-checks active subscriptions on an interval (~1 min). The user only needs to log in, grant access, and link Telegram.
- **Apps Script webhook** (optional): power users can paste a generated `onChange` script for lower latency.
- **Google Drive push** (optional, behind `ENABLE_DRIVE_WEBHOOK`): near real-time, but requires a domain-verified HTTPS backend URL (a custom domain — `*.run.app` cannot be verified).

Concurrency is made safe with a **PostgreSQL advisory lock per subscription**, and the snapshot update inside the locked transaction makes duplicate triggers idempotent.

---

## 🏗️ Architecture

```
            ┌─────────────────────────────┐
            │   Frontend (React + Vite)    │  ← Vercel
            │   Login · Sheets · Logs      │
            └──────────────┬──────────────┘
                           │ HTTPS (JWT)
            ┌──────────────▼──────────────┐
            │   Backend (FastAPI)          │  ← Google Cloud Run
            │   OAuth · Subscriptions      │
            │   Polling worker · Webhooks  │
            └───────┬─────────────┬────────┘
                    │             │
        ┌───────────▼──┐   ┌──────▼───────────┐
        │ Cloud SQL    │   │ Telegram Bot API │
        │ (PostgreSQL) │   │ + Google Sheets  │
        └──────────────┘   └──────────────────┘
```

---

## 🧰 Tech stack

- **Frontend:** React 18, Vite, TailwindCSS, Axios — deployed on **Vercel**.
- **Backend:** FastAPI (Python 3.11), SQLAlchemy 2 (async), httpx — deployed on **Google Cloud Run**.
- **Database:** PostgreSQL (Cloud SQL).
- **Auth:** Google OAuth 2.0 (JWT sessions).
- **Notifications:** Telegram Bot API (webhook mode).

---

## 📁 Project structure

```
backend/
├── main.py                 # FastAPI app + lifespan (polling worker, webhook setup)
├── config.py               # Settings (env-driven)
├── database.py             # Async engine/session
├── models/                 # users, sheet_subscriptions, notification_logs, drive_watch_channels
├── schemas/                # Pydantic request/response models
├── routers/                # auth, sheets, telegram, webhook, logs
└── services/
    ├── auth.py             # Google OAuth + token refresh
    ├── sheets.py           # Google Sheets/Drive API + subscription CRUD
    ├── change_detector.py  # Snapshot diff (cell / range / column / row)
    ├── change_processor.py # Shared engine: pull → diff → notify → log
    ├── notification.py     # Single-message formatting
    ├── telegram.py         # Bot API + account linking
    ├── poller.py           # Background polling loop
    ├── drive_watch.py      # Drive push channels (optional)
    ├── runtime_urls.py     # Public URL resolution
    └── schema_sync.py      # Backward-compatible column adds on startup

frontend/
└── src/
    ├── pages/              # Login, Dashboard, Sheets, Telegram, Logs, Settings
    ├── context/            # AuthContext
    └── lib/api.js          # Axios client
```

---

## 🗄️ Database (what gets logged)

`notification_logs` records every notification, satisfying the "store a log of what was entered + when the Telegram was sent" requirement:

- `spreadsheet_name`, `sheet_name`, `row_number`, `cell_reference`
- `change_type` (insert/update/delete/column_*), `changed_columns`
- `before_data`, `after_data` (the actual values)
- `telegram_message`, `status` (sent/failed/skipped)
- `received_at`, `sent_at` (timestamps)

---

## 🚀 Local development

### Backend
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in your values
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

### Required environment variables (backend `.env`)
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sheetnotify
SECRET_KEY=<random 64-hex>           # python -c "import secrets; print(secrets.token_hex(32))"
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_BOT_USERNAME=<your_bot>
TELEGRAM_WEBHOOK_SECRET=<random>
FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://localhost:8000
ENVIRONMENT=development
ENABLE_POLLING=true
```

Frontend (`.env` / Vercel): `VITE_API_BASE_URL=<backend URL>`

> **Never commit real secrets.** `config.py` defaults are placeholders; supply real values via environment variables.

---

## ☁️ Deployment

- **Backend → Cloud Run:** build from `backend/` (Dockerfile included). For the background polling worker to run reliably, deploy with `--min-instances=1 --no-cpu-throttling` and attach Cloud SQL. Set `BACKEND_URL` to the public service URL and `FRONTEND_URL` to the deployed frontend.
- **Frontend → Vercel:** connect the repo, set `VITE_API_BASE_URL`, deploy. SPA routing is handled by `frontend/vercel.json`.
- **Google OAuth consent screen:** while in *Testing* mode, only added test users can sign in and refresh tokens expire after 7 days. Publish the consent screen to use it more broadly (sensitive/restricted scopes show an "unverified app" notice until Google verification).

---

## ⚠️ Notes & limitations

- Default polling latency is up to ~1 minute (configurable). Real-time requires the optional Apps Script or Drive push paths.
- Sheets are assumed to have a header row (row 1); columns are tracked by header name.
- Telegram must be linked for messages to send; otherwise notifications are logged as `skipped`.
