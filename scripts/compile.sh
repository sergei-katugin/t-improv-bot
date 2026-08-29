#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_python.sh"
cd "$PROJECT_ROOT"

"$PROJECT_PYTHON" -m compileall -q \
  admin_bot public_bot scheduler db alembic tests \
  main.py config.py app_logging.py html_utils.py time_utils.py

echo "Compilation passed."
