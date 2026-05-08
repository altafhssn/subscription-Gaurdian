# Subscription Guardian — Dockerfile
# Deploy via Railway or any container host
FROM python:3.11-slim

WORKDIR /app

# Copy everything in deploy/
COPY . .

# Install deps
RUN pip install --no-cache-dir -r requirements.txt

# Railway passes $PORT, fallback to 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
