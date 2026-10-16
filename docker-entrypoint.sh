#!/bin/sh
set -e

# ==============================================================================
# Telegram Shop Bot Container Entrypoint
# ==============================================================================

# Ensure data directory exists for SQLite database and backups
mkdir -p /app/data

# Auto-seed demo catalog if requested or if flag is present
if [ "${AUTO_SEED}" = "true" ] || [ "${SEED_DEMO}" = "true" ]; then
    echo "📦 Checking and seeding demo catalog into database..."
    python seed_catalog.py || true
fi

# Support running only the FastAPI WebApp server (for external bot embedding)
if [ "$1" = "api" ] || [ "${MODE}" = "api" ]; then
    echo "🚀 Starting FastAPI WebApp Server only on port 8000..."
    exec uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 2
fi

# Default: execute the passed command (usually "python run.py")
exec "$@"
