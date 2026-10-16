# ==============================================================================
# Telegram Shop Bot & Mini App — Production Container
# Multi-purpose container running FastAPI WebApp + Telegram Bot
# ==============================================================================

FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DATA_DIR=/app/data

WORKDIR /app

# Install system dependencies (curl for healthchecks, sqlite3, ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies with pip cache disabled
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/
COPY seed_catalog.py setup_wizard.py run.py ./
COPY docker-entrypoint.sh ./

# Create persistent data volume directory and ensure permissions
RUN mkdir -p /app/data && chmod +x /app/docker-entrypoint.sh

# Expose FastAPI WebApp & webhook server port
EXPOSE 8000

# Health check verifying the FastAPI service is healthy
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "run.py"]
