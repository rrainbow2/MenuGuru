#!/bin/bash
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install Python 3.11+ from python.org, then run this file again."
  read -p "Press Enter to close..."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating the app environment..."
  python3 -m venv .venv
fi

echo "Installing/updating required components..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "Starting Packing Slip Chef System..."
.venv/bin/python -m streamlit run app.py
