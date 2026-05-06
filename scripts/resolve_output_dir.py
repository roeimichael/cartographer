#!/usr/bin/env python3
"""
Helper: pick the output directory for cartographer artifacts.

Default: `<project_root>/.cartographer/`
Readonly: `~/.cartographer/<project-hash>/` — keeps the user's repo clean.

Used by run_pipeline.sh and the SKILL.md flow. Prints the resolved absolute
path on stdout (and nothing else, so callers can `OUTPUT_DIR=$(...)` directly).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path


def project_hash(root: Path) -> str:
    """Stable short hash of the project's absolute path."""
    h = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
    return h[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root")
    ap.add_argument("--readonly", action="store_true",
                    help="Use a global cache dir under $HOME instead of "
                         "writing into the project. Nothing lands in the repo.")
    ap.add_argument("--explicit-output",
                    help="Override: use this exact directory regardless of mode.")
    args = ap.parse_args()

    if args.explicit_output:
        out = Path(args.explicit_output).resolve()
    elif args.readonly or os.environ.get("CARTOGRAPHER_READONLY"):
        h = project_hash(Path(args.project_root))
        cache = Path.home() / ".cartographer" / h
        out = cache.resolve()
    else:
        out = (Path(args.project_root) / ".cartographer").resolve()

    out.mkdir(parents=True, exist_ok=True)
    # Drop a project marker so users can find their output later
    marker = out / "_project.txt"
    marker.write_text(f"{Path(args.project_root).resolve()}\n", encoding="utf-8")

    print(out, end="")


if __name__ == "__main__":
    main()
