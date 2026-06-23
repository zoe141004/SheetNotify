# Sử dụng Python image chính thức, bản nhẹ (slim)
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
