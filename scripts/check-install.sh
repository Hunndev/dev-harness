#!/bin/sh
# Read-only inventory of the seven plugins: repository version vs Claude Code / Codex installs.
# Usage: bash scripts/check-install.sh [--json] [--require hb-be,hb-cm]
# Exit 1 only on a confirmed version mismatch (or a --require plugin that is missing/unknown).
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 exec python3 "$SCRIPT_DIR/check_install.py" "$@"
