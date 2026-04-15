#!/usr/bin/env bash
set -e

PY_BIN=$(command -v python3.11 || command -v python3 || command -v python)

if [ -z "$1" ]; then
  echo "Usage: ./run_sync_secrets.sh owner/repo"
  exit 1
fi

$PY_BIN sync_alert_secrets.py --repo "$1" --with-state
