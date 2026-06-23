🔔 SheetNotify — Full System Prompt & Technical Specification (GCP + Vercel Edition)Mục đích tài liệu này: Đây là prompt/spec đầy đủ để xây dựng nền tảng automation SheetNotify sử dụng Google Cloud Platform (GCP) cho Backend/Database và Vercel cho Frontend.Dùng làm instruction cho AI coding assistant (Claude Code, Cursor, Copilot) hoặc để tự triển khai.1. TỔNG QUAN DỰ ÁNMô tảXây dựng nền tảng SheetNotify — cho phép bất kỳ ai đăng ký tài khoản, kết nối Google Sheet của họ, và nhận thông báo Telegram ngay lập tức mỗi khi có dữ liệu mới được nhập vào sheet đó. Hệ thống hoạt động 24/7 trên hạ tầng Google Cloud Serverless, tối ưu hóa độ trễ kết nối ở mức thấp nhất.Nguyên lý hoạt động (High-level)User nhập dữ liệu vào Google Sheet
        ↓ (onChange trigger)
Google Apps Script (chạy trên server Google, miễn phí 24/7)
        ↓ (HTTP POST webhook - Google internal network)
Google Cloud Run (FastAPI Backend - Serverless Container)
        ↓ (Telegram Bot API)
Telegram message → User's phone
        ↓
Log entry saved → Google Cloud SQL (PostgreSQL)
2. TECH STACK (GCP ALIGNED)LayerTechnologyLý do chọnFrontendReact + Vite + TailwindCSSSPA nhanh, deploy Vercel dễBackendFastAPI (Python 3.11+)Async tốt, chạy cực nhẹ trên Cloud Run containerDatabaseGoogle Cloud SQL (PostgreSQL)Cơ sở dữ liệu chuẩn doanh nghiệp, bảo mật IAM tuyệt đối, dùng credit $300 của GCPBackend DeployGoogle Cloud Run (Serverless)Free 2 triệu req/tháng vĩnh viễn, scale tự động về 0 khi không dùng, mạng nội bộ Google siêu tốcFrontend DeployVercel (static + CDN)Free, tối ưu hóa phân phối toàn cầuAuthGoogle OAuth 2.0 (via authlib)Xác thực chính chủ qua Google AccountSheet DetectionGoogle Apps Script (GAS)Trigger thời gian thực, không tốn tài nguyên serverTelegramTelegram Bot APIWebhook mode, không cần pollingORMSQLAlchemy 2.0 + AlembicQuản lý schema database dễ dàngThư viện Python chínhfastapi==0.111.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.30
alembic==1.13.1
asyncpg==0.29.0           # async PostgreSQL driver
python-jose[cryptography]  # JWT tokens
passlib[bcrypt]
httpx==0.27.0              # async HTTP client
google-auth==2.30.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.134.0
python-multipart==0.0.9
pydantic-settings==2.3.0
python-dotenv==1.0.1
3. KIẾN TRÚC HỆ THỐNG (GCP HOUSING)┌─────────────────────────────────────────────────────┐
│                    VERCEL (Frontend)                 │
│   React SPA — Dashboard, Setup Wizard, Logs          │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS API calls
┌──────────────────────▼──────────────────────────────┐
│         GOOGLE CLOUD PLATFORM (GCP - Backend)        │
│   Google Cloud Run (FastAPI inside Docker)           │
│   ┌─────────────────────────────────────────────┐   │
│   │  /api/auth/*      Google OAuth endpoints     │   │
│   │  /api/sheets/*    Google Sheets management  │   │
│   │  /api/webhook/*   Receive GAS notifications  │   │
│   │  /api/telegram/*  Bot webhook + link flow    │   │
│   │  /api/logs/*      Notification history       │   │
│   └─────────────────────────────────────────────┘   │
└───────────┬──────────────────────┬──────────────────┘
            │                      │
            ▼ (Secure Cloud Proxy) ▼ (Outbound Internet)
┌───────────────────┐   ┌──────────────────────────┐
│ Google Cloud SQL  │   │   TELEGRAM BOT API       │
│ (PostgreSQL)      │   │   api.telegram.org       │
└───────────────────┘   └──────────────────────────┘

External triggers (Google Internal Network):
┌───────────────────────────────────────────────┐
│  Google Apps Script (Google's servers, free)   │
│  - onChange trigger trên Google Sheet          │
│  - POST webhook → Cloud Run Backend            │
└───────────────────────────────────────────────┘
4. DATABASE SCHEMA (PostgreSQL)-- =============================================
-- USERS
-- =============================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    name            VARCHAR(255),
    avatar_url      TEXT,
    google_id       VARCHAR(255) UNIQUE NOT NULL,
    google_access_token   TEXT,
    google_refresh_token  TEXT,
    google_token_expiry   TIMESTAMP WITH TIME ZONE,
    telegram_chat_id      BIGINT UNIQUE,
    telegram_username     VARCHAR(255),
    telegram_linked_at    TIMESTAMP WITH TIME ZONE,
    telegram_link_token   UUID DEFAULT gen_random_uuid() NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_link_token ON users(telegram_link_token);
CREATE INDEX idx_users_google_id ON users(google_id);

-- =============================================
-- SHEET SUBSCRIPTIONS
-- =============================================
CREATE TABLE sheet_subscriptions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    spreadsheet_id      VARCHAR(255) NOT NULL,
    spreadsheet_name    VARCHAR(255),
    spreadsheet_url     TEXT,
    sheet_name          VARCHAR(255) NOT NULL,
    sheet_gid           VARCHAR(50),
    webhook_secret      VARCHAR(255) NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    is_active           BOOLEAN DEFAULT TRUE,
    script_installed    BOOLEAN DEFAULT FALSE,
    last_known_row      INTEGER DEFAULT 1,
    notification_template TEXT DEFAULT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, spreadsheet_id, sheet_name)
);

CREATE INDEX idx_subscriptions_user_id ON sheet_subscriptions(user_id);
CREATE INDEX idx_subscriptions_webhook_secret ON sheet_subscriptions(webhook_secret);

-- =============================================
-- NOTIFICATION LOGS
-- =============================================
CREATE TABLE notification_logs (
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
    source_ip           INET
);

CREATE INDEX idx_logs_user_id ON notification_logs(user_id);
CREATE INDEX idx_logs_subscription_id ON notification_logs(subscription_id);
CREATE INDEX idx_logs_received_at ON notification_logs(received_at DESC);
5. API ENDPOINTS(Base URL mặc định của Cloud Run sẽ có dạng: https://sheetnotify-api-xxxx-uc.a.run.app)Tất cả các định nghĩa API (Authentication, Google Sheets, Telegram, Webhook, Logs) giữ nguyên cấu trúc chuẩn RESTful như Spec gốc.6. GOOGLE APPS SCRIPT — TRIGGER CODE(Giữ nguyên mã nguồn Google Apps Script tự động phát hiện và gửi dữ liệu thông qua Webhook)7. TELEGRAM BOT SETUP(Giữ nguyên thiết lập BotTelegram qua @BotFather)8. FRONTEND PAGES & COMPONENTS(Sử dụng React SPA deploy lên Vercel. Frontend trỏ API về địa chỉ URL của Google Cloud Run)9. NOTIFICATION TEMPLATE ENGINE(Giữ nguyên logic render template và hàm gửi tin nhắn)10. ENVIRONMENT VARIABLES (GCP ENVIRONMENT)Backend (Google Cloud Run Env)# Database Connection (Dùng Socket Path nội bộ của GCP khi deploy, hoặc TCP khi chạy local)
# Local: postgresql+asyncpg://user:pass@localhost:5432/sheetsnotify
# Production (Cloud Run to Cloud SQL): 
DATABASE_URL=postgresql+asyncpg://db_user:db_password@/sheetsnotify?host=/cloudsql/your-gcp-project:us-central1:your-cloudsql-instance

# JWT
SECRET_KEY=your-256-bit-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_DAYS=7

# Google OAuth (Tạo trên GCP Console)
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_REDIRECT_URI=https://sheetnotify-api-xxxx-uc.a.run.app/api/auth/google/callback

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABCdefGHI...
TELEGRAM_WEBHOOK_SECRET=random-webhook-verify-token

# App Config
FRONTEND_URL=https://sheetsnotify.vercel.app
ENVIRONMENT=production
Frontend (Vercel)VITE_API_BASE_URL=https://sheetnotify-api-xxxx-uc.a.run.app
VITE_TELEGRAM_BOT_USERNAME=SheetNotifyBot
11. PROJECT STRUCTURE & DOCKERIZATION (Backend)Vì Cloud Run chạy các ứng dụng được đóng gói dưới dạng Docker, cấu trúc dự án cần có file Dockerfile để GCP tự động build.Cấu trúc thư mục Backend:backend/
├── main.py
├── config.py
├── database.py
├── Dockerfile                  # THÊM MỚI (Dành cho Cloud Run)
├── .dockerignore               # THÊM MỚI
├── models/
├── schemas/
├── routers/
├── services/
├── middleware/
├── alembic/
└── requirements.txt
backend/Dockerfile# Sử dụng Python image chính thức, bản nhẹ (slim)
FROM python:3.11-slim

# Ngăn Python ghi các file .pyc và bật log realtime
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết (cho asyncpg/Postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy toàn bộ mã nguồn vào container
COPY . .

# Cloud Run tự động gán cổng qua biến môi trường PORT (mặc định là 8080)
EXPOSE 8080

# Chạy ứng dụng bằng Uvicorn
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
backend/.dockerignore.git
.venv
__pycache__
*.pyc
.env
alembic.ini
12. DEPLOYMENT GUIDE TO GCPStep 1: Thiết lập Google Cloud SQL (PostgreSQL)Truy cập Google Cloud Console, tạo một project mới.Tìm kiếm Cloud SQL -> Chọn Create Instance -> Chọn PostgreSQL.Chọn cấu hình tối thiểu để tiết kiệm tài nguyên (ví dụ: db-f1-micro hoặc db-custom-1-3840 thuộc Shared-core).Tạo database tên là sheetsnotify và thiết lập tài khoản người dùng (db_user, db_password).Sao chép Connection Name của Instance (dạng: project-id:region:instance-id).Step 2: Kích hoạt các API cần thiết trên GCPKích hoạt các API sau trên GCP Dashboard:Cloud Run APICloud SQL Admin API (Bắt buộc để Cloud Run giao tiếp được với Cloud SQL)Artifact Registry API (Để lưu trữ Docker Image)Google Sheets & Drive APIStep 3: Deploy Backend lên Google Cloud RunSử dụng công cụ Google Cloud CLI (gcloud) để build và deploy thẳng từ máy tính của bạn:# Đăng nhập vào GCP
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Build container bằng Cloud Build và đẩy lên Artifact Registry tự động
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/sheetnotify-backend ./backend

# Deploy container lên Cloud Run
gcloud run deploy sheetnotify-backend \
  --image gcr.io/YOUR_PROJECT_ID/sheetnotify-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --add-cloudsql-instances YOUR_PROJECT_ID:us-central1:YOUR_INSTANCE_ID \
  --set-env-vars DATABASE_URL="postgresql+asyncpg://db_user:db_password@/sheetsnotify?host=/cloudsql/YOUR_PROJECT_ID:us-central1:YOUR_INSTANCE_ID" \
  --set-env-vars SECRET_KEY="your-secret-key" \
  --set-env-vars TELEGRAM_BOT_TOKEN="your-bot-token" \
  --set-env-vars FRONTEND_URL="https://sheetsnotify.vercel.app"
Step 4: Deploy Frontend lên VercelĐẩy code Frontend (React SPA) lên một kho lưu trữ GitHub.Kết nối dự án GitHub này với Vercel Dashboard.Thêm các biến môi trường:VITE_API_BASE_URL = URL của ứng dụng Cloud Run vừa nhận được ở Step 3.VITE_TELEGRAM_BOT_USERNAME = Username của Telegram bot.Nhấn Deploy.Tài liệu này được tối ưu hóa cho kiến trúc Google Cloud Platform Serverless v2.0Cập nhật lần cuối: 06/2026