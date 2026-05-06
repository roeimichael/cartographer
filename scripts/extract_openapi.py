#!/usr/bin/env python3
"""
Phase 1.6 (part 1): Extract or synthesize an OpenAPI spec for the project.

Three strategies tried in order:

  A. **File**: a pre-existing openapi.json/openapi.yaml at one of the usual
     locations (project root, ./docs/, ./openapi/).
  B. **Live**: fetch from a running server at --live-url (e.g.
     http://localhost:8000/openapi.json).
  C. **Synthetic**: build a minimal OpenAPI 3.1 doc from the endpoints we
     already detected statically in project-map.json.

Strategy C always works (zero config). A and B yield richer schemas (real
request/response models, descriptions). The combined output `openapi.json`
in the .cartographer directory is what trace_endpoints.py consumes next.

This script does **not** import the target project's code — that's brittle
and can run arbitrary user code. If you want full schema fidelity, run your
server and pass --live-url instead.
"""
from __future__ import annotations

import argparse
import json
import sys
import re
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

CANDIDATE_FILES = [
    "openapi.json",
    "openapi.yaml",
    "openapi_tmp.json",
    "docs/openapi.json",
    "openapi/openapi.json",
    "schemas/openapi.json",
    "api/openapi.json",
]


def try_file(root: Path):
    for rel in CANDIDATE_FILES:
        p = root / rel
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if rel.endswith(".yaml"):
            try:
                import yaml  # type: ignore
                return yaml.safe_load(text), str(p)
            except Exception:
                continue
        try:
            return json.loads(text), str(p)
        except Exception:
            continue
    return None, None


def try_live(url: str, timeout: int = 5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), url
    except Exception as e:
        print(f"  live fetch failed: {e}", file=sys.stderr)
        return None, None


def synthesize(pmap: dict) -> dict:
    """Build a minimal OpenAPI 3.1 doc from the endpoints we statically detected."""
    paths = defaultdict(dict)
    handler_index = {}
    for ep in pmap.get("endpoints", []):
        method = ep["method"].lower()
        path = ep["path"]
        op_id = (
            ep.get("handler_id", "").rsplit("::", 1)[-1]
            or f"{method}_{path.replace('/', '_').strip('_') or 'root'}"
        )
        handler_index[f"{method.upper()} {path}"] = ep.get("handler_id", "")
        op = {
            "operationId": op_id,
            "summary": "",
            "tags": [Path(ep["file"]).parent.name],
            "x-cartographer": {
                "handler_id": ep.get("handler_id", ""),
                "file": ep["file"],
                "line": ep.get("line", 0),
                "framework": ep.get("framework", ""),
            },
            "responses": {"200": {"description": "OK"}},
        }
        # Path parameters: extract {name} groups
        params = []
        rest = path
        while "{" in rest and "}" in rest:
            i, j = rest.index("{"), rest.index("}")
            name = rest[i + 1 : j]
            params.append({
                "name": name, "in": "path", "required": True,
                "schema": {"type": "string"},
            })
            rest = rest[j + 1:]
        if params:
            op["parameters"] = params
        paths[path][method] = op

    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "Synthetic OpenAPI from project-cartographer",
            "version": "synth",
            "description": "Built from statically detected endpoints. Run the server and use --live-url for richer schemas.",
        },
        "paths": dict(paths),
        "x-cartographer": {
            "synthetic": True,
            "endpoint_count": len(pmap.get("endpoints", [])),
            "handler_index": handler_index,
        },
    }
    return spec


def annotate_with_handlers(spec: dict, pmap: dict) -> dict:
    """For real OpenAPI specs (from file/live), attach our handler_ids so
    trace_endpoints.py can find the call-graph entry point per operation.

    Matches in order:
      1. exact METHOD + path
      2. method + path suffix (handles `app.include_router(prefix='/auth')`)
      3. operationId → handler symbol name (FastAPI defaults to func name)
    """
    # exact-key lookup
    h_exact = {}
    # method+suffix lookup: bucket by (METHOD, last_path_segment)
    h_suffix = []  # list of (method, path, entry)
    # name lookup: handler function name -> entry
    h_by_name = {}
    sym_by_id = {s["id"]: s for s in pmap.get("symbols", [])}

    for ep in pmap.get("endpoints", []):
        entry = {
            "handler_id": ep.get("handler_id", ""),
            "file": ep["file"],
            "line": ep.get("line", 0),
            "framework": ep.get("framework", ""),
        }
        h_exact[f"{ep['method'].upper()} {ep['path']}"] = entry
        h_suffix.append((ep["method"].upper(), ep["path"], entry))
        if entry["handler_id"]:
            sym = sym_by_id.get(entry["handler_id"])
            if sym:
                h_by_name.setdefault(sym["name"], []).append(entry)

    def normalize_path(p: str) -> str:
        # FastAPI vs OpenAPI: parameter forms are usually identical ({id}),
        # but some specs use ":id" (Express). Normalize both.
        return re.sub(r":([A-Za-z_][\w]*)", r"{\1}", p)

    paths = spec.get("paths") or {}
    matched = 0
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, op in list(methods.items()):
            if method.lower() not in {"get", "post", "put", "patch", "delete",
                                       "head", "options", "trace"}:
                continue
            if not isinstance(op, dict):
                continue
            method_u = method.upper()
            np = normalize_path(path)

            # 1. exact
            entry = h_exact.get(f"{method_u} {np}")

            # 2. suffix match: detected_path is the suffix of openapi path
            if not entry:
                best = None
                for det_m, det_p, det_e in h_suffix:
                    if det_m != method_u:
                        continue
                    if np == det_p or np.endswith(det_p):
                        # prefer longer suffixes (more specific match)
                        cand_len = len(det_p)
                        if best is None or cand_len > best[0]:
                            best = (cand_len, det_e)
                if best:
                    entry = best[1]

            # 3. operationId → handler name
            if not entry:
                op_id = op.get("operationId", "")
                # FastAPI default operationId is "<func_name>_<path_basename>_<method>"
                # try matching against any handler name that's a prefix of operationId
                cands = []
                for fn_name, entries in h_by_name.items():
                    if op_id.startswith(fn_name + "_") or op_id == fn_name:
                        for e in entries:
                            if e["handler_id"]:
                                # bonus: prefer one whose method matches
                                cands.append(e)
                if cands:
                    entry = cands[0]

            if entry:
                op.setdefault("x-cartographer", {}).update(entry)
                matched += 1

    print(f"  matched {matched} operations to handlers", file=sys.stderr)

    spec.setdefault("x-cartographer", {})["handler_index"] = {
        f"{m.upper()} {p}": op["x-cartographer"]["handler_id"]
        for p, methods in paths.items() if isinstance(methods, dict)
        for m, op in methods.items()
        if isinstance(op, dict)
        and op.get("x-cartographer", {}).get("handler_id")
    }
    return spec


def render_summary(spec: dict) -> str:
    paths = spec.get("paths") or {}
    info = spec.get("info") or {}
    rows = []
    for p, methods in sorted(paths.items()):
        if not isinstance(methods, dict):
            continue
        for m, op in methods.items():
            if not isinstance(op, dict):
                continue
            tag = (op.get("tags") or [""])[0]
            opid = op.get("operationId", "")
            handler = (op.get("x-cartographer") or {}).get("handler_id", "—")
            rows.append((m.upper(), p, opid, tag, handler))

    md = ["# OpenAPI summary",
          "",
          f"- Title: {info.get('title', '?')}",
          f"- Version: {info.get('version', '?')}",
          f"- Endpoints: {len(rows)}",
          ""]
    if spec.get("x-cartographer", {}).get("synthetic"):
        md.append("**Note:** synthesized from static endpoint detection — schemas are minimal. "
                  "Run your server and pass `--live-url http://localhost:PORT/openapi.json` for full schemas.")
        md.append("")
    md.append("## Endpoints")
    md.append("| Method | Path | Operation | Tag | Handler |")
    md.append("|--------|------|-----------|-----|---------|")
    for r in rows:
        md.append(f"| {r[0]} | `{r[1]}` | `{r[2]}` | {r[3]} | `{r[4]}` |")
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_map", help="Path to project-map.json")
    ap.add_argument("--root", help="Project root (defaults to root from project-map.json)")
    ap.add_argument("--live-url", help="Live server URL to fetch /openapi.json from "
                                       "(e.g. http://localhost:8000/openapi.json)")
    ap.add_argument("--output-dir", "-o", default=".cartographer")
    args = ap.parse_args()

    pmap = json.loads(Path(args.project_map).read_text(encoding="utf-8"))
    root = Path(args.root or pmap.get("root", "."))
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec, source = None, None

    if args.live_url:
        print(f"Trying live fetch: {args.live_url}", file=sys.stderr)
        spec, source = try_live(args.live_url)

    if not spec:
        print(f"Trying file under {root}...", file=sys.stderr)
        spec, source = try_file(root)

    if not spec:
        print("Falling back to synthetic build from project-map endpoints", file=sys.stderr)
        spec = synthesize(pmap)
        source = "synthetic"
    else:
        # we found a real spec — make sure handler_ids are attached
        spec = annotate_with_handlers(spec, pmap)

    out_path = out_dir / "openapi.json"
    out_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    summary_path = out_dir / "openapi_summary.md"
    summary_path.write_text(render_summary(spec), encoding="utf-8")

    n_paths = sum(1 for p, methods in (spec.get("paths") or {}).items()
                  if isinstance(methods, dict))
    n_ops = sum(1 for p, methods in (spec.get("paths") or {}).items()
                if isinstance(methods, dict)
                for m, op in methods.items()
                if isinstance(op, dict))
    print(f"\nSource: {source}", file=sys.stderr)
    print(f"Wrote {out_path}", file=sys.stderr)
    print(f"Wrote {summary_path}", file=sys.stderr)
    print(f"Paths: {n_paths}  Operations: {n_ops}", file=sys.stderr)


if __name__ == "__main__":
    main()
