#!/usr/bin/env bash
set -e

python auto_alert_worker.py --interval 60 --cooldown 10 &
WORKER_PID=$!
echo "[run_all] auto worker started pid=${WORKER_PID}"

after_exit() {
  echo "[run_all] stopping worker pid=${WORKER_PID}"
  kill ${WORKER_PID} 2>/dev/null || true
}
trap after_exit EXIT

streamlit run stock.py
