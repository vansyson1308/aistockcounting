#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT=${BACKUP_ROOT:-/opt/vj-inventory/backups}
KEEP_DAILY=${KEEP_DAILY:-7}

mapfile -t backups < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort -r)
count=0
for b in "${backups[@]}"; do
  count=$((count+1))
  if (( count > KEEP_DAILY )); then
    rm -rf "$b"
  fi
done

echo "Prune complete (daily keep=$KEEP_DAILY). Weekly/monthly retention should be handled by separate archival policy."
