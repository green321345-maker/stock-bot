#!/usr/bin/env bash
set -e

PY_BIN=$(command -v python3.11 || command -v python3 || command -v python)

$PY_BIN auto_alert_worker.py --interval 60 --cooldown 10
