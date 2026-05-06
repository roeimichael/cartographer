#!/usr/bin/env python3
"""
Phase 7: structure a refactor backlog into ready-to-dispatch fix items.

Reads a backlog file (markdown or JSON) and emits a JSON dispatch plan that
the main agent uses to spawn fix subagents (waves of ≤5 in parallel, like
Phase 4).

Backlog item schema (JSON):
    {
      "id": "fix-1",
      "summary": "Move Toasters inside <BrowserRouter>",
      "severity": "P0",
      "files": ["frontend/src/App.tsx"],
      "location": "frontend/src/App.tsx:??",
      "description": "Toasters mounted outside <BrowserRouter>; any toast using useNavigate will crash.",
      "fix": "Move <Toaster /> and <Sonner /> children inside <BrowserRouter>.",
      "verification": "import frontend/src/App.tsx — should parse"
    }

Markdown form: a fenced block per item:

    ```fix-1
    summary: ...
    severity: P0
    files: a.py, b.py
    location: a.py:42
    description: |
      ...
    fix: |
      ...
    verification: ...
    ```

Fix items are grouped into waves so that no two items in the same wave touch
the same file (parallel-safe).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

WAVE_SIZE = 5


def parse_markdown_backlog(text: str) -> list:
    """Parse a backlog markdown file with fenced ```<id> blocks."""
    items = []
    pattern = re.compile(r"```([\w-]+)\n(.*?)```", re.DOTALL)
    for m in pattern.finditer(text):
        item_id, body = m.group(1), m.group(2)
        cur = {"id": item_id}
        # very simple key: value parser, with `|` block scalar support
        lines = body.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            mk = re.match(r"^([\w_]+):\s*(.*)$", line)
            if not mk:
                i += 1
                continue
            key, val = mk.group(1), mk.group(2).strip()
            if val == "|":
                # block scalar — collect indented lines
                buf = []
                i += 1
                while i < len(lines) and (lines[i].startswith("  ") or lines[i] == ""):
                    buf.append(lines[i][2:] if lines[i].startswith("  ") else lines[i])
                    i += 1
                cur[key] = "\n".join(buf).strip()
                continue
            if key == "files":
                cur[key] = [f.strip() for f in val.split(",") if f.strip()]
            else:
                cur[key] = val
            i += 1
        items.append(cur)
    return items


def plan_waves(items, wave_size=WAVE_SIZE):
    """Group items into waves so no two items in a wave touch the same file."""
    remaining = list(items)
    waves = []
    while remaining:
        wave = []
        wave_files = set()
        skip = []
        for item in remaining:
            files = set(item.get("files", []))
            if files & wave_files or len(wave) >= wave_size:
                skip.append(item)
                continue
            wave.append(item)
            wave_files |= files
        waves.append([w["id"] for w in wave])
        remaining = skip
    return waves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("backlog", help="Path to backlog file (markdown or JSON)")
    ap.add_argument("--output", "-o", default=".cartographer/fix_plan.json")
    ap.add_argument("--wave-size", type=int, default=WAVE_SIZE)
    ap.add_argument("--severity-min", default="P3",
                    help="Skip items below this severity (P0 < P1 < P2 < P3)")
    args = ap.parse_args()

    backlog_path = Path(args.backlog)
    text = backlog_path.read_text(encoding="utf-8")
    if backlog_path.suffix == ".json":
        items = json.loads(text)
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
    else:
        items = parse_markdown_backlog(text)

    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    cap = severity_order.get(args.severity_min, 3)
    items = [i for i in items if severity_order.get(i.get("severity", "P3"), 3) <= cap]

    waves = plan_waves(items, wave_size=args.wave_size)

    plan = {
        "items": items,
        "waves": waves,
        "wave_size": args.wave_size,
        "stats": {
            "total_items": len(items),
            "total_waves": len(waves),
            "by_severity": {
                s: sum(1 for i in items if i.get("severity") == s)
                for s in ["P0", "P1", "P2", "P3"]
            },
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    print(f"Wrote {out}", file=sys.stderr)
    print(f"\n{len(items)} items → {len(waves)} waves "
          f"(max {args.wave_size} per wave)", file=sys.stderr)
    for s in ["P0", "P1", "P2", "P3"]:
        n = sum(1 for i in items if i.get("severity") == s)
        if n:
            print(f"  {s}: {n} items", file=sys.stderr)
    for i, w in enumerate(waves, 1):
        print(f"  Wave {i}: {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
