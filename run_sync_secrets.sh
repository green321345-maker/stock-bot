#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
  echo "Usage: ./run_sync_secrets.sh owner/repo"
  exit 1
fi

python sync_alert_secrets.py --repo "$1" --with-state
