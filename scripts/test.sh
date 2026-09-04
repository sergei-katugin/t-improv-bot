#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_python.sh"
cd "$PROJECT_ROOT"

COVERAGE_TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$COVERAGE_TMP_DIR"' EXIT
export COVERAGE_FILE="$COVERAGE_TMP_DIR/.coverage"

if ! "$PROJECT_PYTHON" -c "import pytest" >/dev/null 2>&1; then
  echo "pytest is missing. Install dev dependencies:" >&2
  echo "  $PROJECT_PYTHON -m pip install -r requirements-dev.txt" >&2
  exit 1
fi

"$PROJECT_PYTHON" -m pytest -q \
  --cov=admin_bot --cov=public_bot --cov=scheduler --cov=db \
  --cov=main --cov=miniapp_api --cov=config --cov=time_utils --cov=html_utils \
  --cov-report=term-missing --cov-fail-under=30 \
  "$@"
