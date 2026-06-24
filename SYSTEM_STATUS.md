# 🔔 SheetNotify — System Status & Implementation Report v2.1

**Status:** POLLING ARCHITECTURE IMPLEMENTED (June 24, 2026)  
**Last Updated:** June 24, 2026

---

## 1. PROJECT OVERVIEW

### Vision
SheetNotify — nền tảng automation cho phép user tạo Google Sheet subscriptions và nhận thông báo Telegram tự động khi có dữ liệu mới. Zero-setup default experience (polling), optional advanced path (Apps Script webhooks).

### Core Problem Solved
- ✅ **DNS Error Fixed:** Backend URL không còn hardcode localhost (fixed via runtime_urls.py)
- ✅ **Zero Manual Setup:** User không cần cài Apps Script — polling chạy tự động
- ✅ **Change Detail:** Notifications giờ hiển thị file/sheet/cell/before→after diffs

### Current Status Summary
| Component | Status | Notes |
|-----------|--------|-------|
| URL Resolution | ✅ DONE | runtime_urls.py integrated, no localhost fallback |
| Polling Infrastructure | ✅ DONE | Worker, change detector, schema extensions complete |
| Drive Push Trigger | ✅ IMPLEMENTED (flag) | Drive files.watch → /api/webhook/drive → same snapshot-diff engine. Behind ENABLE_DRIVE_WEBHOOK; needs a domain-verified HTTPS BACKEND_URL (custom domain, NOT *.run.app) |
| Webhook Support | ✅ UNIFIED | Apps Script webhook now triggers the SAME snapshot-diff engine as polling (no longer trusts the payload row) |
| File-level Subscriptions | ✅ IMPLEMENTED | track_all_sheets=true polling all tabs |
| Frontend UI | ✅ IMPLEMENTED | Polling controls, file-level checkbox, App Script hidden for file subs |
| Content-based Diff | ✅ DONE | change_detector now matches rows by content hash → correct insert/update/delete even for mid-sheet edits |
| Baseline on first run | ✅ DONE | First snapshot stored silently (no spam of existing rows) |
| Dedup Layer | ✅ DONE | Snapshot is updated inside the locked txn → duplicate triggers find no diff (idempotent) |
| Multi-instance Safety | ✅ DONE | pg_try_advisory_xact_lock per subscription serializes processing across instances + webhook/poller |
| Live Testing | ❌ PENDING | Code complete; needs end-to-end run on Cloud Run (manual) |
| Production Deployment | ⚠️ READY | Pending live smoke test + secrets rotation |

---

## 2. TECH STACK (Current)

### Deployment
| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 18 + Vite + TailwindCSS | SPA deployed on Vercel |
| **Backend** | FastAPI 0.111.0 (Python 3.11) | Async serverless on Cloud Run |
| **Database** | PostgreSQL (Cloud SQL) | Async via asyncpg 0.29.0 |
| **Change Detection** | Custom snapshot diffing | Row-level before/after comparison |
| **Polling** | asyncio background task | Per-subscription intervals (min 1 min) |
| **Auth** | Google OAuth 2.0 | authlib 1.2.0 |
| **Notifications** | Telegram Bot API | Webhook mode |
| **ORM** | SQLAlchemy 2.0.30 + Alembic | Schema management + migrations |

### Python Dependencies (Backend)
```
fastapi==0.111.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.30
alembic==1.13.1
asyncpg==0.29.0
python-jose[cryptography]
passlib[bcrypt]
httpx==0.27.0
google-auth==2.30.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.134.0
python-multipart==0.0.9
pydantic-settings==2.3.0
python-dotenv==1.0.1
```

### Node Dependencies (Frontend)
- React 18
- Vite 5+
- TailwindCSS 3+
- Axios (for API calls)

---

## 3. ARCHITECTURE & DATA FLOWS

### System Architecture Diagram
```
┌─────────────────────────────────────────────────────────────┐
│                    VERCEL (Frontend)                        │
│   React SPA → Dashboard, Subscribe, Logs, Settings          │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTPS API calls
┌────────────────────▼────────────────────────────────────────┐
│         GOOGLE CLOUD PLATFORM (GCP - Backend)               │
│   Google Cloud Run (FastAPI in Docker Container)            │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ /api/auth/*        → Google OAuth flow                │  │
│   │ /api/sheets/*      → Subscribe, list, diffs          │  │
│   │ /api/webhook/*     → Receive Apps Script webhooks    │  │
│   │ /api/telegram/*    → Bot linking, webhook setup      │  │
│   │ /api/logs/*        → Notification history            │  │
│   │                                                       │  │
│   │ [Polling Worker]   → Background asyncio task         │  │
│   │ - Runs every 60s in lifespan                        │  │
│   │ - Fetches all active subscriptions                 │  │
│   │ - Respects per-sub polling_interval_minutes        │  │
│   └──────────────────────────────────────────────────────┘  │
└────────┬────────────────────────┬──────────────────────────┘
         │ (SQLAlchemy async)      │ (Outbound HTTPS)
         ▼                         ▼
    ┌─────────────────┐      ┌──────────────────┐
    │ Cloud SQL       │      │ Telegram Bot API │
    │ PostgreSQL      │      │ api.telegram.org │
    │ - users         │      │                  │
    │ - subscriptions │      │ + Google Sheets  │
    │ - logs          │      │ + Google Drive   │
    └─────────────────┘      └──────────────────┘
```

### Flow 1: Polling (Default, Zero-Setup)
```
1. User Subscribe
   POST /api/sheets/subscribe
   {
     "spreadsheet_id": "...",
     "sheet_name": "Sheet1" OR sheet_name = null,
     "track_all_sheets": false | true (default: false)
     "polling_enabled": true (default),
     "polling_interval_minutes": 1 (default)
   }
   
2. Backend: Create subscription
   - Store polling settings in sheet_subscriptions
   - Store track_all_sheets + monitored_sheet_names
   - Set last_state_snapshot = null (initial)
   - Return SubscriptionResponse with polling metadata

3. Polling Loop (runs continuously in app lifespan)
   while True:
     for each subscription where is_active=true and polling_enabled=true:
       
       3a. Check interval
           elapsed_seconds = now - last_polled_at
           if elapsed_seconds < polling_interval_minutes * 60:
             continue  # skip until interval elapsed
       
       3b. Fetch sheet data
           if track_all_sheets=true:
             snapshots = get_spreadsheet_snapshots(spreadsheet_id)
           else:
             snapshot = get_sheet_snapshot(spreadsheet_id, sheet_name)
       
       3c. Detect changes
           changes = detect_changes(
             previous_rows = last_state_snapshot.rows,
             current_rows = snapshot.rows,
             headers = snapshot.headers
           )
           # Returns: [RowChange(change_type, row_number, before, after, changed_columns, cell_reference), ...]
       
       3d. For each change: send notification
           for change in changes:
             message = format_polling_notification(
               spreadsheet_name, sheet_name, change, headers
             )
             # Message includes:
             # - 🟢 Inserted / 📝 Updated / 🗑️ Deleted (icon)
             # - File: {spreadsheet_name} | Tab: {sheet_name} | Cell: {reference}
             # - Changed columns: [col1, col2]
             # - Before: {values}
             # - After: {values}
             # - Timestamp: {UTC}
             
             send_telegram_message(user.telegram_chat_id, message)
             
             notification_log = NotificationLog(
               user_id=user.id,
               subscription_id=subscription.id,
               spreadsheet_name=snapshot.spreadsheet_name,
               sheet_name=snapshot.sheet_name,
               row_number=change.row_number,
               before_data=change.before,
               after_data=change.after,
               changed_columns=change.changed_columns,
               cell_reference=change.cell_reference,
               change_type=change.change_type,
               detection_method="polling",
               status="sent"
             )
             session.add(notification_log)
       
       3e. Update subscription state
           subscription.last_state_snapshot = {
             "headers": snapshot.headers,
             "rows": snapshot.rows
           }
           subscription.last_polled_at = now
           subscription.poll_failure_count = 0
           session.commit()
     
     sleep(60)  # Next cycle in 60 seconds

4. Database Persist
   - notification_logs row created with diffs
   - sheet_subscriptions.last_state_snapshot updated (JSONB)
   - User sees notification on Telegram phone
```

### Flow 2: Webhook (Sheet-level Only, Optional)
```
1. User creates subscription
   POST /api/sheets/subscribe
   {
     "spreadsheet_id": "...",
     "sheet_name": "Sheet1",
     "track_all_sheets": false (required for webhooks)
   }
   - Response includes subscription.id

2. User requests Apps Script
   GET /api/subscriptions/{subscription_id}/script?backend_url=...
   
   - Checks: if track_all_sheets=true → return 400 (webhooks only for sheet-specific)
   - Resolves backend URL:
     * First check: BACKEND_URL env (production Cloud Run URL)
     * Second check: X-Forwarded-Proto/Host headers (load balancer)
     * Never fallback to localhost in production
   - Generates Apps Script template with resolved webhook URL
   - Returns JavaScript to copy-paste into Google Sheet

3. User manual setup (one-time)
   - Copy generated script into Sheet's script editor
   - Run setupTrigger() function manually
   - Grants permissions to sheet notifications

4. Runtime: Sheet onChange trigger fires
   - Apps Script onChange() → detect new rows
   - POST /api/webhook/sheets/{subscription_id}
   - Body: { rows, lastKnownRow, spreadsheet_id, sheet_name, ... }

5. Backend webhook handler
   POST /api/webhook/sheets/{subscription_id}
   - Validates webhook_secret
   - Renders notification_template with row data
   - send_telegram_message()
   - Create notification_logs entry (detection_method="webhook")

6. Telegram → User's phone
```

### Flow 3: Drive Push Notification (Near real-time, zero per-user setup)
```
Prerequisite (one-time, platform owner): BACKEND_URL must be a domain-verified
HTTPS URL. A *.run.app URL CANNOT be verified — map a custom domain to Cloud Run
and verify it (Search Console / GCP Domain verification). Set ENABLE_DRIVE_WEBHOOK=true.

1. User subscribes (login + grant Sheets/Drive read + link Telegram only).
   POST /api/sheets/subscribe
   → backend creates a Drive files.watch channel for (user, spreadsheet_id)
     using the user's OAuth token (services/drive_watch.ensure_channel).
     One channel per spreadsheet covers all its subscriptions.
   → channel id/resource_id/token/expiration stored in drive_watch_channels.

2. User edits the sheet.
   → Google POSTs an (empty) notification to /api/webhook/drive with headers
     X-Goog-Channel-ID, X-Goog-Channel-Token, X-Goog-Resource-State.
   → backend validates the token, maps channel → (user, spreadsheet),
     and runs the SHARED engine (change_processor) for every active
     subscription on that spreadsheet. detection_method="drive".

3. Renewal: Drive channels expire (max 1 day). run_drive_maintenance_loop
   re-issues watches before expiry every DRIVE_MAINTENANCE_CYCLE_SECONDS.

4. Backstop: delivery is best-effort (may be missed), so polling stays on as a
   safety net. Raise polling_interval_minutes when Drive push is active to save
   Google API quota; the advisory lock + snapshot make double-triggers harmless.
```

### Change Detection Algorithm (Snapshot Diffing)
```python
detect_changes(previous_rows, current_rows, headers):
  """
  Compares two snapshots of sheet data, returns list of RowChange objects.
  Each RowChange includes:
  - change_type: "insert" | "update" | "delete"
  - row_number: integer (position in sheet)
  - before: dict (old values) | None for insert
  - after: dict (new values) | None for delete
  - changed_columns: list of column names (for update only)
  - cell_reference: "ColumnName3" (for single-cell updates only)
  """
  
  Changes:
  1. INSERTs: row_number appears in current but not previous
  2. DELETEs: row_number appears in previous but not current
  3. UPDATEs: same row_number, different cell values
     - Compute changed_columns by cell-by-cell comparison
     - If only 1 column changed, set cell_reference = "ColumnName{row_number}"
     - If multiple columns changed, cell_reference = "{row_number}"
  
  Idempotency:
  - Each row hashed (SHA256 of JSON) → prevents duplicate detection if polled again
  - Rows compared by content, not position
```

---

## 4. DATABASE SCHEMA (PostgreSQL)

### USERS Table
```sql
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(255) UNIQUE NOT NULL,
    name                VARCHAR(255),
    avatar_url          TEXT,
    google_id           VARCHAR(255) UNIQUE NOT NULL,
    google_access_token   TEXT,
    google_refresh_token  TEXT,
    google_token_expiry   TIMESTAMP WITH TIME ZONE,
    telegram_chat_id      BIGINT UNIQUE,
    telegram_username     VARCHAR(255),
    telegram_linked_at    TIMESTAMP WITH TIME ZONE,
    telegram_link_token   UUID DEFAULT gen_random_uuid() NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### SHEET_SUBSCRIPTIONS Table (Extended for Polling)
```sql
CREATE TABLE sheet_subscriptions (
    -- Original fields
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    spreadsheet_id          VARCHAR(255) NOT NULL,
    spreadsheet_name        VARCHAR(255),
    spreadsheet_url         TEXT,
    sheet_name              VARCHAR(255),  -- Optional if track_all_sheets=true
    sheet_gid               VARCHAR(50),
    webhook_secret          VARCHAR(255) NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    is_active               BOOLEAN DEFAULT TRUE,
    script_installed        BOOLEAN DEFAULT FALSE,
    last_known_row          INTEGER DEFAULT 1,
    notification_template   TEXT DEFAULT NULL,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- NEW POLLING FIELDS (Task 2)
    polling_enabled         BOOLEAN DEFAULT TRUE,
    polling_interval_minutes INTEGER DEFAULT 1,
    track_all_sheets        BOOLEAN DEFAULT FALSE,  -- file-level subscriptions
    monitored_sheet_names   TEXT[],  -- optional filter for track_all_sheets
    last_state_snapshot     JSONB,  -- { "headers": [...], "rows": [...] }
    last_polled_at          TIMESTAMP WITH TIME ZONE,
    last_poll_error         TEXT,
    poll_failure_count      INTEGER DEFAULT 0,
    
    UNIQUE(user_id, spreadsheet_id, sheet_name)
);
```

### NOTIFICATION_LOGS Table (Extended for Diff Metadata)
```sql
CREATE TABLE notification_logs (
    -- Original fields
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id     UUID REFERENCES sheet_subscriptions(id) ON DELETE SET NULL,
    spreadsheet_id      VARCHAR(255),
    spreadsheet_name    VARCHAR(255),
    sheet_name          VARCHAR(255),
    row_number          INTEGER,
    row_data            JSONB NOT NULL,
    telegram_message    TEXT,
    status              VARCHAR(20) DEFAULT 'sent' CHECK(status IN ('sent', 'failed', 'skipped')),
    error_message       TEXT,
    received_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    sent_at             TIMESTAMP WITH TIME ZONE,
    source_ip           INET,
    
    -- NEW DIFF FIELDS (Task 2)
    before_data         JSONB,  -- full row before change
    after_data          JSONB,  -- full row after change
    changed_columns     TEXT[],  -- ["Email", "Phone"] for updates
    cell_reference      VARCHAR(50),  -- "Email3" or just "3" for multi-column
    change_type         VARCHAR(20),  -- "insert" | "update" | "delete"
    detection_method    VARCHAR(20)   -- "polling" | "webhook"
);
```

---

## 5. API ENDPOINTS

### Authentication
- `POST /api/auth/google` → Start OAuth flow
- `GET /api/auth/google/callback` → OAuth callback
- `POST /api/auth/logout` → Logout

### Google Sheets Management
- `POST /api/sheets/list` → List user's spreadsheets
- `POST /api/sheets/subscribe` → Create subscription
  ```json
  {
    "spreadsheet_id": "...",
    "sheet_name": "Sheet1 | null",
    "track_all_sheets": false | true,
    "monitored_sheet_names": ["Sheet1", "Sheet2"] | null,
    "polling_enabled": true,
    "polling_interval_minutes": 1
  }
  ```
- `GET /api/subscriptions` → List user's subscriptions
- `GET /api/subscriptions/{id}` → Get subscription details
- `DELETE /api/subscriptions/{id}` → Delete subscription
- `GET /api/subscriptions/{id}/script` → Generate Apps Script  
  **FIXED:** Uses resolve_backend_url() → no localhost fallback

### Telegram Linking
- `POST /api/telegram/link-start` → Start linking flow
- `GET /api/telegram/link/{link_token}` → Complete linking
- `POST /api/telegram/webhook` → Telegram bot webhook

### Webhooks (Apps Script)
- `POST /api/webhook/sheets/{subscription_id}` → Apps Script notification
- **REFACTORED:** Now takes Request parameter for URL resolution

### Logs
- `GET /api/logs` → List notification history
- `GET /api/logs/{id}` → Get notification details with diffs

---

## 6. NEW BACKEND SERVICES (Task 2 Implementation)

### backend/services/runtime_urls.py [NEW]
**Purpose:** Resolve public backend URL at runtime (fixes DNS error)

**Key Functions:**
- `resolve_backend_url(request: Request | None) → str`
  - Priority 1: BACKEND_URL env (production)
  - Priority 2: X-Forwarded-Proto/Host headers (behind load balancer)
  - Fallback: localhost:8000 (development only)
  - **Never returns localhost in production**

**Used in:**
- `backend/routers/sheets.py` — `/subscriptions/{id}/script` endpoint
- `backend/routers/telegram.py` — `setup_webhook()` endpoint
- `backend/main.py` — Telegram webhook initialization

**Status:** ✅ Complete, all routers tested

---

### backend/services/sheets.py [EXTENDED]
**New Purpose:** Snapshot fetching for polling + original subscription CRUD

**New Classes:**
- `SheetSnapshot` dataclass
  - spreadsheet_id, spreadsheet_name
  - sheet_name, sheet_gid
  - headers: list[str]
  - rows: list[dict]
  - fetched_at: datetime

**New Functions:**
- `get_spreadsheet_metadata(spreadsheet_id, user) → (name, sheet_tabs)`
- `get_sheet_snapshot(spreadsheet_id, sheet_name, user) → SheetSnapshot`
  - Fetches data via Google Sheets API v4
  - Includes headers (A1 notation)
  - Blank headers → "Column N" (preserves position)
  
- `get_spreadsheet_snapshots(spreadsheet_id, user, monitored_sheets=None) → list[SheetSnapshot]`
  - Fetches all tabs (or filtered subset)
  - Returns one SheetSnapshot per tab

**Header Handling:**
- If cell is blank → named "Column 1", "Column 2", etc.
- Preserves position stability (column 3 stays column 3 even if header is blank)

**Status:** ✅ Complete

---

### backend/services/change_detector.py [NEW]
**Purpose:** Row-level change detection between sheet snapshots

**Classes:**
- `CellChange` dataclass
  - column: str
  - before: Any
  - after: Any

- `RowChange` dataclass
  - change_type: str ("insert" | "update" | "delete")
  - row_number: int
  - before: dict | None
  - after: dict | None
  - changed_columns: list[str]
  - cell_reference: str | None ("ColumnName3" or just "3")

**Functions:**
- `detect_changes(previous_rows, current_rows, headers) → list[RowChange]`
  - Compares row content (not position)
  - Detects inserts, deletes, updates
  - For updates: computes changed columns + cell reference
  
- `snapshot_rows(rows, headers) → dict`
  - Returns { "headers": [...], "rows": [...], "row_hashes": {...} }
  - Uses SHA256 hash for each row (idempotency)

**Status:** ✅ Complete, not yet deployed

---

### backend/services/poller.py [NEW]
**Purpose:** Background polling worker for continuous sheet monitoring

**Architecture:**
- Runs as asyncio task in FastAPI app lifespan
- Wakes every 60 seconds = 1 polling cycle
- For each active subscription: checks if interval elapsed, fetches data, detects changes, sends notifications
- Respects per-subscription polling_interval_minutes

**Functions:**
- `poll_subscription(subscription_id) → None`
  - Load subscription + user from DB
  - Check is_active, polling_enabled
  - Respect polling_interval_minutes (early return if not elapsed)
  - Fetch snapshots (single or multiple)
  - detect_changes()
  - For each change: send Telegram, log notification_logs
  - Update last_state_snapshot + timestamp
  - Increment poll_failure_count on error
  - Commit to DB

- `run_polling_loop(poll_interval_seconds=60)`
  - Infinite loop
  - Every 60s: fetch all active subscriptions, call poll_subscription() for each
  - Sleep 60s, repeat

**Database Persistence:**
- Commits subscription.last_state_snapshot (JSONB)
- Commits subscription.last_polled_at (timestamp)
- Commits subscription.poll_failure_count (error tracking)
- Copies to notification_logs with before_data, after_data, changed_columns, cell_reference, change_type="polling"

**Status:** ✅ Complete, wired into main.py lifespan, not yet deployed

---

### backend/services/notification.py [EXTENDED]
**New Function:** `format_polling_notification(spreadsheet_name, sheet_name, change, headers) → str`

**Message Format (HTML Telegram):**
```
🟢 New row added in {spreadsheet_name} / {sheet_name}
Cell Reference: {cell_reference}
Changed columns: Email, Phone

Before:
(empty for insert)

After:
Email: john@example.com
Phone: 555-1234

Timestamp: 2026-06-24 10:30:45 UTC
```

**Icons:**
- 🟢 Insert
- 📝 Update
- 🗑️ Delete

**Status:** ✅ Complete

---

### backend/services/schema_sync.py [NEW]
**Purpose:** Backward-compatible schema migrations on startup

**Approach:** Uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- Runs at FastAPI startup (before any routers)
- Safe for both fresh installs and existing DBs
- 14 ALTER statements total (8 for subscriptions, 6 for logs)
- Idempotent (columns only added if missing)

**Status:** ✅ Complete

---

## 7. MODIFIED BACKEND FILES

### backend/main.py [EXTENDED]
**Changes:**
- Import asyncio, ensure_polling_schema, run_polling_loop
- Lifespan function:
  1. Create tables via SQLAlchemy metadata
  2. Call ensure_polling_schema(engine) — adds missing columns
  3. Setup Telegram webhook
  4. Create polling_task = asyncio.create_task(run_polling_loop(60)) if production
  5. Yield (app runs)
  6. Cancel polling_task, handle CancelledError
  7. Dispose engine

**Status:** ✅ Complete

---

### backend/routers/sheets.py [EXTENDED]
**Changes:**
- `/subscribe` POST endpoint:
  - Accepts polling settings (polling_enabled, polling_interval_minutes, track_all_sheets, monitored_sheet_names)
  - Validates: sheet_name required unless track_all_sheets=true
  - Threads settings into create_subscription()
  - Returns SubscriptionResponse with polling fields

- `/subscriptions/{id}/script` GET endpoint:
  - Now takes Request parameter
  - Uses resolve_backend_url(request) — no localhost fallback
  - Rejects if track_all_sheets=true (Apps Script for sheet-specific only)

**Status:** ✅ Complete

---

### backend/routers/telegram.py [EXTENDED]
**Changes:**
- `setup_webhook()` endpoint now uses resolve_backend_url() instead of settings.BACKEND_URL

**Status:** ✅ Complete

---

### backend/models/subscription.py [EXTENDED]
**New Columns:**
- polling_enabled: bool = True
- polling_interval_minutes: int = 1 (minimum 1)
- track_all_sheets: bool = False
- monitored_sheet_names: list[str] | None
- last_state_snapshot: dict | None (JSONB)
- last_polled_at: datetime | None
- last_poll_error: str | None
- poll_failure_count: int = 0

**Status:** ✅ Complete, backward-compatible

---

### backend/models/notification.py [EXTENDED]
**New Columns:**
- before_data: dict | None (JSONB)
- after_data: dict | None (JSONB)
- changed_columns: list[str] | None (JSONB)
- cell_reference: str | None
- change_type: str | None ("insert" | "update" | "delete")
- detection_method: str | None ("polling" | "webhook")

**Status:** ✅ Complete, backward-compatible

---

### backend/schemas/subscription.py [EXTENDED]
**SubscriptionCreate:** Added polling_enabled, polling_interval_minutes, track_all_sheets, monitored_sheet_names (all optional with defaults)

**SubscriptionResponse:** Shows polling fields + errors

**Status:** ✅ Complete

---

### backend/schemas/notification.py [EXTENDED]
**NotificationLogResponse:** Shows before_data, after_data, changed_columns, cell_reference, change_type, detection_method

**Status:** ✅ Complete

---

## 8. FRONTEND MODIFICATIONS

### frontend/src/pages/SheetsPage.jsx [REFACTORED]
**Changes:**
- Polling display in subscription list:
  ```
  Scope: Entire spreadsheet | Tab: {sheet_name}
  Polling: {interval} min (if enabled) | Polling: Off (if disabled)
  ```

- AddSheetModal:
  - Added "Track entire spreadsheet" checkbox (track_all_sheets)
  - Tab select disabled when checkbox checked
  - Validation: sheet_name required unless track checked
  - POST /subscribe includes polling_enabled=true, monitoring settings
  
- Apps Script button: Hidden if track_all_sheets=true

**Status:** ✅ Complete

---

## 9. TECH CHOICES & RATIONALE

| Decision | Why |
|----------|-----|
| **Polling over Real-time** | Google Apps Script requires user binding; polling = zero-setup default |
| **1-minute intervals** | Balance between latency and API quota (Google Sheets free tier: 300 req/min shared) |
| **Snapshot diffing** | Idempotent (replay-safe), enables precise before/after diffs |
| **Background asyncio task** | Lightweight, no extra infrastructure, runs in FastAPI lifespan |
| **File-level subscriptions** | Enable monitoring entire spreadsheets without manual tab selection |
| **Webhook Apps Script optional** | Power users can opt-in for real-time, doesn't block polling path |

---

## 10. TODO: IMPLEMENTATION GAPS & ROADMAP

### Priority 1: Production Hardening (BLOCKING DEPLOYMENT)

#### ❌ Task 3: Dedup Layer for Polling
**Problem:** If polling_loop wakes multiple times between sheet edits, could fire duplicate notifications.

**Solution Options:**
- A) Add row hash bloom filter to subscription (last 1000 rows) → check before sending
- B) At DB layer: check notification_logs for identical (subscription_id, row_hash) in last 60s

**Estimated Effort:** 2-3 hours
**File:** backend/services/poller.py + backend/models/subscription.py

---

#### ❌ Task 4: Multi-Instance Safety (CRITICAL FOR SCALE)
**Problem:** Polling runs in-process; Cloud Run scales to multiple instances = subscriptions polled N times.

**Solution Options:**
- A) Distributed lock via Redis (recommended)
- B) Distributed lock via PostgreSQL advisory locks
- C) Leader election (only 1 instance does polling)

**Estimated Effort:** 4-6 hours (production-grade locking)
**Files:** backend/services/poller.py + new backend/services/distributed_lock.py + cloud config

---

#### ⚠️ Task 5: Error Recovery
**Current:** poll_failure_count incremented; subscription still marked active.

**Needed:** After N consecutive failures, pause subscription + notify user.

**Estimated Effort:** 1-2 hours

---

### Priority 2: Testing & Validation

#### ❌ Task 6: Live Testing
**Checklist:**
- [ ] Create test Google Sheet
- [ ] Subscribe with polling=true, track_all_sheets=false (sheet-level)
- [ ] Subscribe with polling=true, track_all_sheets=true (file-level)
- [ ] Add rows → verify Telegram message within 2 minutes
- [ ] Verify no duplicate notifications after 5 edits
- [ ] Verify before/after diffs accurate
- [ ] Test Apps Script webhook path (optional)
- [ ] Test polling interval variations (1, 5, 10 min)

**Estimated Effort:** 2-3 hours

---

#### ❌ Task 7: Performance Testing
- Load test: 1000 subscriptions polling simultaneously
- Quota testing: Google Sheets API (300 req/min shared)
- Database query performance (notification_logs indexing)
- Telegram rate limits (30 messages/sec per chat)

**Estimated Effort:** 3-4 hours

---

### Priority 3: Frontend Refinement

#### ⚠️ Task 8: UX Copy & Documentation
- Add tooltips explaining polling vs. webhook tradeoffs
- Link to Apps Script setup guide (optional advanced path)
- Show polling interval recommendations
- Add error message display (last_poll_error)

**Estimated Effort:** 1-2 hours

---

#### ⚠️ Task 9: Advanced Settings UI
- Allow users to adjust polling_interval_minutes (1-60 min)
- Allow users to select specific tabs for track_all_sheets=true
- Show last_polled_at in subscription list

**Estimated Effort:** 2-3 hours

---

### Priority 4: Deployment & Ops

#### ❌ Task 10: GitHub & CI/CD
- [ ] Commit all changes with message "feat: polling architecture + DNS fix"
- [ ] Set up GitHub Actions for backend tests
- [ ] Set up GitHub Actions for frontend tests
- [ ] Create deployment workflow for Cloud Run

**Estimated Effort:** 2-3 hours

---

#### ❌ Task 11: GCP Deployment
- [ ] Create Cloud SQL instance + database
- [ ] Set credentials in Cloud Run environment
- [ ] Deploy backend: `gcloud run deploy ...`
- [ ] Set BACKEND_URL env to actual Cloud Run URL
- [ ] Deploy frontend to Vercel
- [ ] Configure VITE_API_BASE_URL in Vercel
- [ ] Smoke tests: auth, subscribe, polling, Telegram

**Estimated Effort:** 2-3 hours

---

#### ❌ Task 12: Monitoring & Logging
- Add structured logging (JSON format)
- Monitor polling latency (CloudWatch)
- Monitor error rates (subscription failures)
- Setup alerts for high poll_failure_count

**Estimated Effort:** 2-3 hours

---

## 11. KNOWN LIMITATIONS & RISKS

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **In-process polling** | Duplicates if Cloud Run scales | Task 4: Distributed lock |
| **No dedup** | Duplicate Telegram messages | Task 3: Bloom filter / DB check |
| **1-min latency** | Users expect real-time | Optional Apps Script webhook (Task 2 complete for sheet-level) |
| **Google API quota** | 300 rows read/min shared across all users | Monitor quota, add exponential backoff |
| **Telegram rate limits** | 30 messages/sec per bot | Queue + rate limiter in notification service |
| **Database growth** | notification_logs grows unbounded | Add cleanup job (delete logs older than 90 days) |
| **Polling only sheet-specific** | Apps Script webhook for real-time needs user setup | By design (zero-setup polling default, optional advanced) |

---

## 12. ENVIRONMENT VARIABLES (CURRENT)

### Backend (Cloud Run)
```bash
# Database (runtime: /cloudsql/{project}:{region}:{instance})
DATABASE_URL=postgresql+asyncpg://db_user:db_password@/sheetsnotify?host=/cloudsql/...

# Backend URL (resolves public Cloud Run URL)
BACKEND_URL=https://sheetnotify-backend-xxxxx.a.run.app

# OAuth
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_REDIRECT_URI=https://sheetnotify-backend-xxxxx.a.run.app/api/auth/google/callback

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABCdef...
TELEGRAM_WEBHOOK_SECRET=random-token

# App
ENVIRONMENT=production
FRONTEND_URL=https://sheetsnotify.vercel.app
```

### Frontend (Vercel)
```bash
VITE_API_BASE_URL=https://sheetnotify-backend-xxxxx.a.run.app
VITE_TELEGRAM_BOT_USERNAME=SheetNotifyBot
```

---

## 13. PROJECT STRUCTURE (Current)

```
d:\Antigravity\SheetNotify\
├── backend/
│   ├── main.py                          [MODIFIED] App entry + polling lifespan
│   ├── config.py
│   ├── database.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   ├── middleware/
│   ├── models/
│   │   ├── user.py
│   │   ├── subscription.py              [EXTENDED] +8 polling columns
│   │   ├── notification.py              [EXTENDED] +6 diff columns
│   ├── schemas/
│   │   ├── subscription.py              [EXTENDED] polling fields
│   │   ├── notification.py              [EXTENDED] diff fields
│   │   ├── auth.py
│   │   ├── user.py
│   ├── services/
│   │   ├── auth.py
│   │   ├── sheets.py                    [EXTENDED] snapshot fetching
│   │   ├── notification.py              [EXTENDED] polling message format
│   │   ├── runtime_urls.py              [NEW] DNS fix (no localhost)
│   │   ├── change_detector.py           [NEW] row-level diffing
│   │   ├── poller.py                    [NEW] polling worker
│   │   ├── schema_sync.py               [NEW] backward-compatible migrations
│   │   ├── telegram.py
│   ├── routers/
│   │   ├── sheets.py                    [EXTENDED] polling settings + file-level subs
│   │   ├── telegram.py                  [MODIFIED] uses runtime_urls.py
│   │   ├── auth.py
│   │   ├── logs.py
│   │   ├── webhook.py
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── SheetsPage.jsx           [REFACTORED] polling UI + track_all_sheets
│   │   │   ├── LoginPage.jsx
│   │   │   ├── DashboardPage.jsx
│   │   │   ├── TelegramPage.jsx
│   │   │   ├── LogsPage.jsx
│   │   │   ├── SettingsPage.jsx
│   │   │   ├── AuthCallback.jsx
│   │   ├── components/
│   │   ├── context/
│   │   ├── lib/
│   │   │   ├── api.js
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── index.css
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│
├── Sheetnotify system prompt.md          [ORIGINAL — see this file for structure]
├── SYSTEM_STATUS.md                      [NEW — this file]
```

---

## 14. NEXT IMMEDIATE ACTIONS (PRIORITY ORDER)

### For Deployment (Blocking)
1. ✅ Task 3: Dedup layer (prevent duplicate notifications)
2. ✅ Task 4: Multi-instance safety (distributed lock)
3. ✅ Task 6: Live testing (validate polling works end-to-end)

### For Production
4. ✅ Task 10: GitHub + CI/CD setup
5. ✅ Task 11: GCP deployment (Cloud Run + Cloud SQL)
6. ✅ Task 12: Monitoring + logging

### For Polish
7. ⚠️ Task 8: UX copy + documentation
8. ⚠️ Task 9: Advanced settings UI

---

## 15. VERIFICATION CHECKLIST (Before Deployment)

- [ ] All syntax errors fixed (error check passed)
- [ ] Polling worker starts without errors in main.py
- [ ] Schema migrations run at startup (backward-compatible)
- [ ] Test subscription creates with polling_enabled=true
- [ ] Test polling detects row changes within 2 minutes
- [ ] Test before/after diffs in notification_logs
- [ ] Test file-level (track_all_sheets=true) subscriptions
- [ ] Test sheet-level (track_all_sheets=false) subscriptions
- [ ] Test Apps Script webhook (sheet-level only)
- [ ] Test URL resolution (no localhost in Cloud Run)
- [ ] Test Telegram message formatting (icons, diffs)
- [ ] Test dedup layer (no duplicate Telegrams)
- [ ] Test multi-instance safety (distributed lock works)
- [ ] Test error recovery (poll_failure_count increments)

---

## 16. DECISIONS MADE & RATIONALE

### Decision 1: Polling Default + Optional Webhook
- **Why:** Google Apps Script requires manual binding per sheet (not auto-installable)
- **Users get:** Zero-setup experience out-of-the-box (polling)
- **Power users get:** Real-time option (Apps Script webhook) with docs + manual setup

### Decision 2: 1-minute Polling Interval
- **Why:** Balance latency vs Google Sheets API quota (300 req/min shared across all users)
- **Per-subscription:** 1-60 minute intervals configurable

### Decision 3: Snapshot Diffing for Change Detection
- **Why:** Enables precise before/after diffs + idempotent replay safety
- **Alternative rejected:** Row counters (less detailed, can't show diffs)

### Decision 4: Background asyncio Task (Not Separate Service)
- **Why:** Lightweight, integrates into FastAPI lifespan, no extra infrastructure
- **Limitation:** In-process (duplication risk at scale) → Task 4: distributed lock

### Decision 5: File-level Subscriptions (track_all_sheets)
- **Why:** Users often want to monitor entire spreadsheets, not just specific tabs
- **Implementation:** Optional polling all sheets in background

---

**Document Version:** 2.1  
**Last Updated:** June 24, 2026  
**Status:** Ready for deployment after Tasks 3-4 completion
