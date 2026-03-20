#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${MSYSTEM:-}" ]] && command -v winpty &>/dev/null; then
    winpty python snake.py
else
    python3 snake.py
fi
