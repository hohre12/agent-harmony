#!/bin/bash
# Agent Harmony runtime bootstrap.
# Ensures Python venv exists, then runs the given Python script.
# Called transparently by .mcp.json — users never see this.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="${VENV_DIR}/bin/python3"

# Bootstrap on first run (or if venv is missing)
if [ ! -f "$PYTHON" ]; then
    python3 -m venv "$VENV_DIR" 2>/dev/null || python -m venv "$VENV_DIR"
fi

# Run the requested script
exec "$PYTHON" "$@"
