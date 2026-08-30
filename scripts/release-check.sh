#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_313:-python3.13}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.13 is required. Set PYTHON_313 to its executable." >&2
  exit 1
fi
if [[ -z "${TEST_POSTGRES_URL:-}" ]]; then
  echo "TEST_POSTGRES_URL must point to a disposable PostgreSQL database." >&2
  exit 1
fi

"$PYTHON_BIN" -m pip install --require-hashes -r requirements.lock
PROJECT_PYTHON_OVERRIDE="$PYTHON_BIN" ./scripts/check.sh
"$PYTHON_BIN" -m alembic heads
