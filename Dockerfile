# ── Stage 1: 프론트엔드 빌드 ──────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ .
RUN npm run build
# 결과물: /app/frontend/../backend/static  (vite.config.js의 outDir)


# ── Stage 2: 백엔드 런타임 ────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Python 의존성
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 백엔드 코드
COPY backend/ .

# 프론트엔드 빌드 결과물 복사
COPY --from=frontend-build /app/backend/static ./static

EXPOSE 8000

# Shell form so ${PORT} env var is expanded at runtime
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
