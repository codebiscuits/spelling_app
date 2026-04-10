#!/usr/bin/env bash
set -euo pipefail

# === Configuration ===
REPO="/mnt/main_backup"
ARCHIVE_NAME="$(date +%Y-%m-%d)"
PASSPHRASE="your-passphrase-here"
LOG_FILE="/var/log/borg-backup.log"

# Export variables for Borg
export BORG_PASSPHRASE="$PASSPHRASE"
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes

# Redirect stdout and stderr to the log file
exec >> "$LOG_FILE" 2>&1

echo "=== Backup started: $(date) ==="

# === Pre-backup checks ===
# (Add checks here, e.g., mount -a or checking if $REPO exists)

# === Create archive ===
# Note the '$' before REPO and ARCHIVE_NAME
borg create --stats --progress --compression zstd,3 \
    "$REPO"::"$ARCHIVE_NAME" \
    /mnt/files/Documents \
    /mnt/files/Music \
    /mnt/files/Pictures \
    /mnt/files/Videos

# === Prune old archives ===
borg prune -v --list --keep-daily=7 --keep-weekly=4 --keep-monthly=6 "$REPO"

# === Compact (borg 1.2+) ===
borg compact "$REPO"

echo "=== Backup finished: $(date) ==="
