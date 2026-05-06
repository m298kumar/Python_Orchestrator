# ── Stage 1: Build Frontend ──────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python Runtime ──────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

# System dependencies for ChromaDB native extensions + Playwright browser deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxfixes3 libxrandr2 libgbm1 libasound2 && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml ./
COPY requirements.txt* ./
RUN pip install --no-cache-dir -e "." 2>/dev/null || \
    pip install --no-cache-dir . 2>/dev/null || \
    (test -f requirements.txt && pip install --no-cache-dir -r requirements.txt)

# Install Playwright browser binaries (chromium only — ~130 MB)
RUN playwright install chromium

# Application code
COPY stlc_platform/ ./stlc_platform/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Create non-root user
RUN adduser --system --group --no-create-home stlc && \
    mkdir -p /app/output /app/feedback && \
    chown -R stlc:stlc /app

# Environment defaults
ENV STLC_SERVE_FRONTEND=true \
    STLC_AUTH_ENABLED=false \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

USER stlc

CMD ["python", "-m", "uvicorn", "stlc_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
