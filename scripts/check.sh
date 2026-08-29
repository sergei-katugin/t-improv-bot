#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/compile.sh"
"$SCRIPT_DIR/test.sh" "$@"

echo "All checks passed."
