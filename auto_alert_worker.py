#!/usr/bin/env python3
"""Background alert worker for full automatic webhook notifications."""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests
import yfinance as yf

ALERT_RULES_FILE = Path("alert_rules.json")
ALERT_STATE_FILE = Path("alert_state.json")


def load_rules_from_env() -> Dict[str, dict]:
    raw = os.getenv("ALERT_RULES_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_state_from_env() -> Dict[str, float]:
    raw = os.getenv("ALERT_STATE_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def safe_num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def send_webhook(url: str, provider: str, payload: dict):
    if provider == "discord":
        lines = [f"📢 {payload.get('ticker', '-')}"]
        for a in payload.get("alerts", []):
            lines.append(f"- {a}")
        lines.append(f"price: {payload.get('price', '-')}")
        lines.append(f"time: {payload.get('time', '-')}")
        body = {"content": "\n".join(lines)}
        r = requests.post(url, json=body, timeout=8)
    else:
        r = requests.post(url, json=payload, timeout=8)
    return r.status_code


def check_once(cooldown_min: int) -> List[str]:
    rules_env = load_rules_from_env()
    state_env = load_state_from_env()
    rules: Dict[str, dict] = rules_env if rules_env else load_json(ALERT_RULES_FILE, {})
    state: Dict[str, float] = state_env if state_env else load_json(ALERT_STATE_FILE, {})
    sent: List[str] = []
    now_ts = time.time()

    for ticker, rule in rules.items():
        webhook_url = rule.get("webhook_url")
        if not webhook_url:
            continue

        provider = rule.get("provider", "discord")
        buy_below = safe_num(rule.get("buy_below", 0))
        sell_above = safe_num(rule.get("sell_above", 0))

        try:
            info = yf.Ticker(ticker).info
            current = safe_num(info.get("currentPrice", 0))
        except Exception:
            continue

        alerts = []
        if buy_below > 0 and current <= buy_below:
            alerts.append(f"[매수신호] {ticker} 현재가 {current} <= {buy_below}")
        if sell_above > 0 and current >= sell_above:
            alerts.append(f"[매도신호] {ticker} 현재가 {current} >= {sell_above}")
        if not alerts:
            continue

        key = f"{ticker}|{'|'.join(alerts)}"
        if now_ts - float(state.get(key, 0)) < cooldown_min * 60:
            continue

        payload = {
            "ticker": ticker,
            "alerts": alerts,
            "price": current,
            "time": datetime.now(timezone.utc).isoformat(),
            "source": "Stock Bot Auto Worker",
        }
        code = send_webhook(webhook_url, provider, payload)
        if 200 <= code < 300:
            state[key] = now_ts
            sent.append(f"{ticker}: {', '.join(alerts)}")

    if not state_env:
        save_json(ALERT_STATE_FILE, state)
    return sent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    parser.add_argument("--cooldown", type=int, default=10, help="Cooldown in minutes")
    parser.add_argument("--once", action="store_true", help="Run only once then exit")
    args = parser.parse_args()

    if args.once:
        sent = check_once(cooldown_min=args.cooldown)
        print(f"[worker-once] sent={len(sent)}")
        for x in sent:
            print(" -", x)
        return

    print(f"[worker] started interval={args.interval}s cooldown={args.cooldown}m")
    while True:
        sent = check_once(cooldown_min=args.cooldown)
        if sent:
            print(f"[worker] sent {len(sent)} alert(s)")
            for x in sent:
                print(" -", x)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
