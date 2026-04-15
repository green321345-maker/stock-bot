#!/usr/bin/env bash
set -e

PY_BIN=$(command -v python3.11 || command -v python3 || command -v python)

$PY_BIN auto_alert_worker.py --interval 60 --cooldown 10 &
WORKER_PID=$!
echo "[run_all] auto worker started pid=${WORKER_PID}"

after_exit() {
  echo "[run_all] stopping worker pid=${WORKER_PID}"
  kill ${WORKER_PID} 2>/dev/null || true
}
trap after_exit EXIT

streamlit run stock.py
