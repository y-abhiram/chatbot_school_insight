#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
/home/jony/miniconda3/bin/python - <<'PY'
from pathlib import Path
import os,secrets
p=Path('.runtime/services.env')
if not p.exists():
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write('PRODUCT_POSTGRES_PASSWORD='+secrets.token_urlsafe(36)+'\n')
PY
if docker compose version >/dev/null 2>&1; then
  docker compose --env-file .runtime/services.env -f compose.yml up -d postgres redis
else
  docker-compose --env-file .runtime/services.env -f compose.yml up -d postgres redis
fi
