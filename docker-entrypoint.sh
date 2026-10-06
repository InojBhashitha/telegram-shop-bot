#!/bin/sh
set -e

# Ensure runtime directories exist
mkdir -p /app/data /app/backups

echo "🚀 [Cloud Deals] Running database migrations..."
if python -m alembic upgrade head; then
    echo "✅ [Cloud Deals] Database migrations applied successfully."
else
    echo "⚠️ [Cloud Deals] Alembic upgrade encountered an issue, continuing startup..."
fi

echo "🌟 [Cloud Deals] Starting application..."
exec "$@"
