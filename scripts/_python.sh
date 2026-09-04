#!/usr/bin/env bash

# Shared Python resolver. This file is sourced by the public scripts.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${PROJECT_PYTHON_OVERRIDE:-}" ]]; then
  PROJECT_PYTHON="$PROJECT_PYTHON_OVERRIDE"
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PROJECT_PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PROJECT_PYTHON="$(command -v python3)"
else
  echo "Python not found. Create .venv or install Python 3." >&2
  exit 1
fi

PROJECT_PYCACHE_DIR="${TMPDIR:-/tmp}/t-impro-bot-pycache"
mkdir -p "$PROJECT_PYCACHE_DIR"
export PYTHONPYCACHEPREFIX="$PROJECT_PYCACHE_DIR"
