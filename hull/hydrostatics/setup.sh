#!/bin/sh
set -eu
INSTALL_ONLY=false
if [ "${1:-}" = "--install-only" ]; then
    INSTALL_ONLY=true
    shift
fi
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"${PYTHON:-python3}" -m venv "$HERE/.venv"
"$HERE/.venv/bin/python" -m pip install -r "$HERE/requirements.txt"
if [ "$INSTALL_ONLY" = true ]; then
    exit 0
fi
"$HERE/.venv/bin/python" "$HERE/v4-2026-10-30/run_navaltoolbox.py" "$@"
