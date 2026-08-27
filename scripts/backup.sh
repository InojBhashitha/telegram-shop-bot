#!/bin/bash
# Cloud Deals — SQLite Database Backup Script
# Usage: ./scripts/backup.sh [backup_dir]

set -e

BACKUP_DIR="${1:-./backups}"
DB_FILE="./cloud_deals.db"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/cloud_deals_${TIMESTAMP}.db"

# Create backup directory
mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_FILE" ]; then
    echo "Error: Database file not found: $DB_FILE"
    exit 1
fi

# Use SQLite's .backup command for a consistent copy
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

echo "Backup created: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"

# Remove backups older than 30 days
find "$BACKUP_DIR" -name "cloud_deals_*.db" -mtime +30 -delete 2>/dev/null || true
echo "Old backups cleaned (>30 days)"
