#!/usr/bin/env bash
# Run on the EC2 host; never mount the Docker socket into the app containers.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
backup_root="${DEPLOY_BACKUP_DIRECTORY:-deployment-backups}"
backup_folder="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_root"
mkdir "$backup_folder"
bash scripts/production.sh exec -T postgres pg_dump -U postgres -d school_ai -Fc > "$backup_folder/database.dump"
# Stop writes briefly while archiving runtime files if a strict DB/PDF snapshot is needed.
bash scripts/production.sh exec -T backend tar -C /app -czf - .runtime > "$backup_folder/runtime.tar.gz"
sha256sum "$backup_folder/database.dump" "$backup_folder/runtime.tar.gz" > "$backup_folder/SHA256SUMS"
printf 'Backup saved to %s. Copy it to encrypted off-instance storage.\n' "$backup_folder"
