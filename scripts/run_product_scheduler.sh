#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
exec /home/jony/miniconda3/bin/python -m celery -A product.jobs.celery beat --loglevel=warning --schedule .runtime/celerybeat-schedule
