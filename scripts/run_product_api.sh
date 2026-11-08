#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
exec /home/jony/miniconda3/bin/python -m uvicorn product.api:app --host 127.0.0.1 --port 8100
