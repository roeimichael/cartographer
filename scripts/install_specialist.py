#!/usr/bin/env python3
"""
Install specialist agents from skills.sh on demand.

Reads `agents/_registry.yml`, matches user-requested integrations, prints
the install command, and (with --execute) runs it.

This is **opt-in** — the skill never auto-installs. Workflow:

  1. Phase 3.5 detects a coverage gap and writes specialist_gaps.json.
  2. Main agent surfaces gaps to user via prompts/specialist_gap.md.
  3. User says "install graphql, solana".
  4. Main agent calls this script with --execute --integrations graphql,solana.
  5. Script confirms the registry has matches, prints install commands,
     and (with --execute) runs `npx skills add <pkg>` for each.
  6. Re-run match_specialists.py to pick up the new agents.

Why is this not automatic? Two reasons:
  - Running `npx skills add` is a system-level state change (installs files).
    Users may want to pin specialist versions, audit before install, or skip
    entirely. Auto-install in a "review" tool would be hostile.
  - skills.sh registry contents change. The registry file ships unverified;
    install confirms the package exists at install time.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def parse_registry(path: Path) -> dict:
    """Tiny YAML-ish parser (avoid pyyaml dep). Same flat structure as agent
    frontmatter parser in match_specialists.py."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict = {}
    current_key = None
    current_obj: dict | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and not line.startswith("\t") and stripped.endswith(":"):
            current_key = stripped[:-1].strip()
            current_obj = {}
            out[current_key] = current_obj
            continue
        if current_obj is not None and ":" in stripped:
            k, _, v = stripped.partition(":")
            current_obj[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="agents/_registry.yml",
                    help="Path to specialist registry YAML")
    ap.add_argument("--integrations", required=True,
                    help="Comma-separated integration labels to install for "
                         "(e.g. 'graphql,solana')")
    ap.add_argument("--execute", action="store_true",
                    help="Actually run `npx skills add ...`. Default: dry-run.")
    ap.add_argument("--log", default=".cartographer/specialist_install.log",
                    help="Log file for install commands run")
    ap.add_argument("--allow-skill-install", action="store_true",
                    help="Required to actually run installs. Without this, "
                         "even --execute will refuse. Two flags = "
                         "deliberate choice.")
    args = ap.parse_args()

    registry = parse_registry(Path(args.registry))
    if not registry:
        print(f"Registry empty or unreadable at {args.registry}.", file=sys.stderr)
        print("Cannot suggest packages. Populate agents/_registry.yml first.",
              file=sys.stderr)
        return 1

    requested = [i.strip() for i in args.integrations.split(",") if i.strip()]
    plan = []
    missing = []
    for label in requested:
        entry = registry.get(label)
        if not entry or not entry.get("package"):
            missing.append(label)
            continue
        plan.append((label, entry))

    if missing:
        print(f"\nNo registry entry for: {', '.join(missing)}", file=sys.stderr)
        print("These integrations don't have a known specialist on skills.sh.",
              file=sys.stderr)
        print("If you find / build one, add an entry to agents/_registry.yml.",
              file=sys.stderr)

    if not plan:
        print("Nothing to install.", file=sys.stderr)
        return 1

    print("\n=== Install plan ===", file=sys.stderr)
    for label, entry in plan:
        verified = "✓" if entry.get("verified") == "true" else "?"
        print(f"  [{verified}] {label}: {entry.get('install', 'npx skills add ' + entry['package'])}",
              file=sys.stderr)
        if entry.get("verified") != "true":
            print(f"       (NOT verified — install may fail; skills.sh registry "
                  f"contents shift over time)", file=sys.stderr)

    if not args.execute:
        print("\nDry-run only. Pass --execute --allow-skill-install to run.",
              file=sys.stderr)
        return 0

    if not args.allow_skill_install:
        print("\nRefusing to run installs without --allow-skill-install.",
              file=sys.stderr)
        print("This double-flag protects against accidental system-level installs.",
              file=sys.stderr)
        return 1

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rc_total = 0
    with log_path.open("a", encoding="utf-8") as logf:
        for label, entry in plan:
            cmd = entry.get("install") or f"npx skills add {entry['package']}"
            print(f"\nRunning: {cmd}", file=sys.stderr)
            logf.write(f"$ {cmd}\n")
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            logf.write(r.stdout)
            logf.write(r.stderr)
            logf.write(f"\n[exit {r.returncode}]\n\n")
            if r.returncode != 0:
                print(f"  failed (exit {r.returncode}) — see {log_path}",
                      file=sys.stderr)
                rc_total = 1
            else:
                print(f"  installed {entry['package']}", file=sys.stderr)

    print(f"\nLog: {log_path}", file=sys.stderr)
    if rc_total == 0:
        print("All installs succeeded. Re-run scripts/match_specialists.py "
              "to pick up the new agents.", file=sys.stderr)
    return rc_total


if __name__ == "__main__":
    sys.exit(main())
