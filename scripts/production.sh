#!/usr/bin/env bash
# Keep production isolated from the original local compose.yml and .env.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "${COMPOSE_BIN:-}" ]]; then
  exec "$COMPOSE_BIN" --env-file .env.production -f compose.production.yml "$@"
fi
exec docker compose --env-file .env.production -f compose.production.yml "$@"
