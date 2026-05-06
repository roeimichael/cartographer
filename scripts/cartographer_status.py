#!/usr/bin/env python3
"""
`cartographer status` — show current run state.

Reads .cartographer/_progress.json and prints a summary. Useful for users
running long phases who want to know what's happening right now without
re-running anything.

Usage:
    python scripts/cartographer_status.py [--output-dir .cartographer]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=".cartographer")
    args = ap.parse_args()

    p = Path(args.output_dir) / "_progress.json"
    if not p.exists():
        print("No active run. (No _progress.json found.)")
        return 0

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"_progress.json present but unreadable: {e}", file=sys.stderr)
        return 1

    elapsed = time.time() - data.get("started", time.time())
    print(f"Phase:    {data.get('phase')}")
    print(f"Step:     {data.get('step')}")
    if data.get("total"):
        pct = (data["current"] / data["total"]) * 100
        print(f"Progress: {data['current']}/{data['total']} ({pct:.0f}%)")
    if data.get("message"):
        print(f"Note:     {data['message']}")
    print(f"Elapsed:  {elapsed:.0f}s")
    print(f"Updated:  {time.time() - data.get('updated', time.time()):.0f}s ago")

    return 0


if __name__ == "__main__":
    sys.exit(main())
