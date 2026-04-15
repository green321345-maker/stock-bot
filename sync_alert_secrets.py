#!/usr/bin/env python3
"""Sync local alert JSON files to GitHub Actions secrets.

Usage:
  python sync_alert_secrets.py --repo owner/repo [--with-state]

Prerequisites:
  - GitHub CLI (`gh`) installed
  - `gh auth login` completed with permission to set repo secrets
"""

import argparse
import subprocess
from pathlib import Path


def run(cmd):
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/name")
    parser.add_argument("--with-state", action="store_true", help="Also sync ALERT_STATE_JSON")
    args = parser.parse_args()

    rules_file = Path("alert_rules.json")
    if not rules_file.exists():
        raise FileNotFoundError("alert_rules.json not found. Save alert rules first in app.")

    rules_json = rules_file.read_text(encoding="utf-8")
    run(["gh", "secret", "set", "ALERT_RULES_JSON", "--repo", args.repo, "--body", rules_json])
    print("[sync] ALERT_RULES_JSON updated")

    if args.with_state:
        state_file = Path("alert_state.json")
        state_json = state_file.read_text(encoding="utf-8") if state_file.exists() else "{}"
        run(["gh", "secret", "set", "ALERT_STATE_JSON", "--repo", args.repo, "--body", state_json])
        print("[sync] ALERT_STATE_JSON updated")


if __name__ == "__main__":
    main()
