"""
Progress heartbeat — tiny shared helper.

Each script that takes more than ~10s should write progress updates to
`.cartographer/_progress.json` so the orchestrator (or a separate `cartographer
status` invocation) can show what's currently happening.

Format (single JSON object overwritten in place):

    {
      "phase": "phase-1",
      "step": "parsing",
      "current": 142,
      "total": 350,
      "message": "parsed 142 files",
      "started": 1746543210.5,
      "updated": 1746543219.2
    }

This module is intentionally dependency-free and tiny so every script can
import it without adding cost. Call `start(phase)` once, then `update(...)`
freely. `done()` clears the file.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

_state = {"phase": "", "started": 0.0, "path": None}


def _resolve_path(out_dir: Optional[Path] = None) -> Path:
    if out_dir is None:
        out_dir = Path(os.environ.get("CARTOGRAPHER_OUTPUT", ".cartographer"))
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "_progress.json"


def start(phase: str, out_dir: Optional[Path] = None):
    _state["phase"] = phase
    _state["started"] = time.time()
    _state["path"] = _resolve_path(out_dir)
    update(step="starting", current=0, total=0, message="")


def update(step: str = "",
           current: int = 0,
           total: int = 0,
           message: str = "",
           **extra):
    if not _state.get("path"):
        return
    payload = {
        "phase": _state["phase"],
        "step": step,
        "current": current,
        "total": total,
        "message": message,
        "started": _state["started"],
        "updated": time.time(),
    }
    payload.update(extra)
    try:
        _state["path"].write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        # don't let progress writes ever crash the actual work
        pass


def done():
    if not _state.get("path"):
        return
    try:
        if _state["path"].exists():
            _state["path"].unlink()
    except Exception:
        pass
