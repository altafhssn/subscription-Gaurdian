# Subscription Guardian — Backend
# H7: non-root user; pinned base image; healthcheck
FROM python:3.11-slim

# Install security updates
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create non-root user
RUN useradd -m -u 1001 appuser

# Copy and install dependencies first (layer cache)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Own files as appuser
RUN chown -R appuser:appuser /app

USER appuser

# H8: expose DB_PATH so it can be overridden to a mounted volume
ENV DB_PATH=/app/data/subguard.db
RUN mkdir -p /app/data

EXPOSE 8000

# Healthcheck hits /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Railway passes $PORT; fallback to 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
