#!/bin/sh
# Lancement sous Linux / macOS
cd "$(dirname "$0")"
if [ ! -d venv ]; then
  python3 -m venv venv && ./venv/bin/pip install -r requirements.txt || exit 1
fi
./venv/bin/python app.py
