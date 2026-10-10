#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required. Install Python 3 and Tkinter for your operating system." >&2
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
fi

if ! ".venv/bin/python" -c "import tkinter, requests, yt_dlp" >/dev/null 2>&1; then
    ".venv/bin/python" -m pip install -r requirements.txt
fi

exec ".venv/bin/python" app.py
