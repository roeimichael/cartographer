#!/usr/bin/env python3
"""
Phase 1.6 (part 2): Per-endpoint deep static call trace.

For each endpoint in openapi.json, do a focused deep BFS through the resolved
call graph from the handler symbol. Output a per-endpoint card with:

  - method, path, summary, tag
  - request schema (from OpenAPI)
  - response schema(s) (from OpenAPI)
  - call tree (deeper than pipelines.json — default depth 10)
  - external dependencies (top 15 unresolved callees with counts — these
    are the boundary: framework/stdlib/3rd-party calls)
  - internal modules touched (file path → call count)
  - cross-endpoint reuse: which other endpoints reach the same internal nodes

This is the "simulated debug trace" — not a real runtime profile, but a
strict over-approximation of every internal function the endpoint *could*
call. Combined with OpenAPI for the I/O surface, it gives a clear picture
of each endpoint's blast radius.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

DEFAULT_MAX_DEPTH = 10
DEFAULT_MAX_NODES = 120


def safe_id(s: str, max_len=80):
    return re.sub(r"\W+", "_", s)[:max_len].strip("_") or "x"


def safe_filename(s: str, max_len=80):
    s = re.sub(r"[^A-Za-z0-9_\-.]", "_", s)
    return re.sub(r"_+", "_", s)[:max_len].strip("_") or "endpoint"


def trace(handler_id, calls_by_caller, max_depth, max_nodes):
    nodes = {handler_id}
    edges = set()
    external = []
    visited = {handler_id}
    queue = deque([(handler_id, 0)])

    while queue and len(nodes) < max_nodes:
        cur, d = queue.popleft()
        if d >= max_depth:
            continue
        for c in calls_by_caller.get(cur, []):
            if c["callee_id"]:
                edges.add((cur, c["callee_id"]))
                if c["callee_id"] not in visited:
                    visited.add(c["callee_id"])
                    nodes.add(c["callee_id"])
                    queue.append((c["callee_id"], d + 1))
            else:
                external.append(c["callee_name"])

    ext_counter = Counter(external)
    return {
        "nodes": sorted(nodes),
        "edges": sorted(edges),
        "external_top": ext_counter.most_common(15),
        "external_total": sum(ext_counter.values()),
    }


def render_endpoint_md(op_info, trace_info, sym_by_id, reuse_map):
    method = op_info["method"]
    path = op_info["path"]
    op_id = op_info["operationId"]
    handler_id = op_info["handler_id"]

    md = [f"# `{method} {path}`", ""]
    md.append(f"- **operationId**: `{op_id}`")
    md.append(f"- **tag**: {op_info.get('tag', '—')}")
    md.append(f"- **handler**: `{handler_id}`" if handler_id else "- **handler**: _(not resolved — endpoint not linked to project-map)_")
    md.append(f"- **call tree size**: {len(trace_info['nodes'])} nodes, {len(trace_info['edges'])} edges")
    md.append(f"- **external calls**: {trace_info['external_total']} (top 15 below)")
    md.append("")

    # Request
    md.append("## Request")
    if op_info.get("parameters"):
        md.append("### Parameters")
        md.append("| Name | In | Required | Type | Description |")
        md.append("|------|-----|----------|------|-------------|")
        for p in op_info["parameters"]:
            schema = p.get("schema") or {}
            t = schema.get("type") or schema.get("$ref", "—")
            md.append(f"| `{p.get('name')}` | {p.get('in')} | {p.get('required', False)} | {t} | {p.get('description', '')} |")
    else:
        md.append("_No parameters._")
    md.append("")

    rb = op_info.get("requestBody")
    if rb:
        md.append("### Body")
        content = (rb or {}).get("content") or {}
        for ctype, item in content.items():
            schema = item.get("schema") or {}
            ref = schema.get("$ref")
            if ref:
                md.append(f"- `{ctype}`: `{ref}`")
            else:
                md.append(f"- `{ctype}`: `{schema.get('type', '?')}`")
        md.append("")

    # Responses
    md.append("## Responses")
    for code, resp in (op_info.get("responses") or {}).items():
        content = (resp or {}).get("content") or {}
        if not content:
            md.append(f"- **{code}**: {resp.get('description', '')}")
            continue
        for ctype, item in content.items():
            schema = item.get("schema") or {}
            ref = schema.get("$ref") or schema.get("type", "?")
            md.append(f"- **{code}** ({ctype}): `{ref}`")
    md.append("")

    # Call tree
    md.append("## Internal call tree")
    if not handler_id:
        md.append("_Handler not linked — no call tree available._")
    elif len(trace_info["nodes"]) <= 1:
        md.append("_Handler has no internal calls — leaf-only endpoint._")
    else:
        md.append("```mermaid")
        md.append("flowchart LR")
        # node defs
        seen = set()
        for nid in trace_info["nodes"]:
            if nid in seen:
                continue
            seen.add(nid)
            s = sym_by_id.get(nid)
            label = (f"{s['name']}<br/><small>{s['file']}:{s['line']}</small>"
                     if s else nid)
            md.append(f'  {safe_id(nid)}["{label}"]')
        # edges
        for caller, callee in trace_info["edges"]:
            md.append(f"  {safe_id(caller)} --> {safe_id(callee)}")
        md.append(f"  {safe_id(handler_id)}:::entry")
        md.append("classDef entry fill:#fef3c7,stroke:#d97706,stroke-width:2px")
        md.append("```")
    md.append("")

    # Internal modules touched
    md.append("## Internal modules touched")
    files_count = Counter()
    for nid in trace_info["nodes"]:
        s = sym_by_id.get(nid)
        if s:
            files_count[s["file"]] += 1
    if files_count:
        md.append("| File | Symbols touched |")
        md.append("|------|------------------|")
        for f, c in files_count.most_common(15):
            md.append(f"| `{f}` | {c} |")
    else:
        md.append("_None._")
    md.append("")

    # External dependencies
    md.append("## External dependencies (top 15)")
    if trace_info["external_top"]:
        md.append("| Callee | Count |")
        md.append("|--------|-------|")
        for name, count in trace_info["external_top"]:
            md.append(f"| `{name}` | {count} |")
    else:
        md.append("_None or all internal._")
    md.append("")

    # Cross-endpoint reuse
    md.append("## Cross-endpoint reuse")
    if not handler_id:
        md.append("_Not available._")
    else:
        # internal nodes (excluding the handler itself) that are also reached
        # by other endpoints' traces
        my_nodes = set(trace_info["nodes"]) - {handler_id}
        shared = []
        for nid in my_nodes:
            also_in = sorted(
                {ep_key for ep_key in reuse_map.get(nid, ()) if ep_key != f"{method} {path}"}
            )
            if also_in:
                s = sym_by_id.get(nid)
                shared.append((nid, s, also_in))
        if not shared:
            md.append("_No symbols shared with other endpoints._")
        else:
            md.append("Symbols this endpoint shares with other endpoints (top 20):")
            md.append("")
            md.append("| Symbol | Also called from |")
            md.append("|--------|------------------|")
            for nid, s, also in shared[:20]:
                label = f"`{s['name']}` (`{s['file']}:{s['line']}`)" if s else f"`{nid}`"
                also_str = ", ".join(f"`{x}`" for x in also[:6])
                if len(also) > 6:
                    also_str += f", … (+{len(also) - 6})"
                md.append(f"| {label} | {also_str} |")
    md.append("")

    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_map", help="Path to project-map.json")
    ap.add_argument("--openapi", default=None,
                    help="Path to openapi.json (default: alongside project-map)")
    ap.add_argument("--output-dir", "-o", default=".cartographer")
    ap.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    ap.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES)
    args = ap.parse_args()

    pmap = json.loads(Path(args.project_map).read_text(encoding="utf-8"))
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spec_path = Path(args.openapi or out_dir / "openapi.json")
    if not spec_path.exists():
        print(f"openapi.json not found at {spec_path}. Run extract_openapi.py first.",
              file=sys.stderr)
        sys.exit(1)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    sym_by_id = {s["id"]: s for s in pmap["symbols"]}
    calls_by_caller = defaultdict(list)
    for c in pmap.get("calls", []):
        if c.get("callee_id"):
            calls_by_caller[c["caller_id"]].append(c)

    # Pass 1: trace each endpoint
    operations = []
    for path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete",
                                       "head", "options", "trace"}:
                continue
            if not isinstance(op, dict):
                continue
            xc = op.get("x-cartographer") or {}
            handler_id = xc.get("handler_id", "")
            op_info = {
                "method": method.upper(),
                "path": path,
                "operationId": op.get("operationId", ""),
                "tag": (op.get("tags") or [""])[0],
                "handler_id": handler_id,
                "parameters": op.get("parameters") or [],
                "requestBody": op.get("requestBody"),
                "responses": op.get("responses") or {},
            }
            if handler_id:
                t = trace(handler_id, calls_by_caller, args.max_depth, args.max_nodes)
            else:
                t = {"nodes": [], "edges": [], "external_top": [], "external_total": 0}
            operations.append((op_info, t))

    # Pass 2: build reuse map (which endpoints reach which internal nodes)
    reuse_map = defaultdict(set)
    for op_info, t in operations:
        key = f"{op_info['method']} {op_info['path']}"
        for nid in t["nodes"]:
            reuse_map[nid].add(key)

    # Write outputs
    endpoints_dir = out_dir / "endpoints"
    endpoints_dir.mkdir(parents=True, exist_ok=True)

    summary_data = []
    for op_info, t in operations:
        # write per-endpoint card
        fname = safe_filename(f"{op_info['method']}_{op_info['path']}") + ".md"
        (endpoints_dir / fname).write_text(
            render_endpoint_md(op_info, t, sym_by_id, reuse_map),
            encoding="utf-8",
        )
        summary_data.append({
            "method": op_info["method"],
            "path": op_info["path"],
            "operationId": op_info["operationId"],
            "tag": op_info["tag"],
            "handler_id": op_info["handler_id"],
            "card_file": f"endpoints/{fname}",
            "node_count": len(t["nodes"]),
            "edge_count": len(t["edges"]),
            "external_total": t["external_total"],
            "external_top": t["external_top"],
            "modules_touched": sorted({sym_by_id[n]["file"] for n in t["nodes"] if n in sym_by_id}),
        })

    (out_dir / "endpoints.json").write_text(
        json.dumps({"endpoints": summary_data,
                    "stats": {
                        "total_endpoints": len(summary_data),
                        "linked_to_handler": sum(1 for e in summary_data if e["handler_id"]),
                        "max_depth": args.max_depth,
                        "max_nodes_per_endpoint": args.max_nodes,
                    }}, indent=2),
        encoding="utf-8",
    )

    # combined index (one mermaid subgraph per top-N endpoints by node count)
    top = sorted(summary_data, key=lambda e: -e["node_count"])[:15]
    idx_md = ["# Endpoint trace index",
              f"- Total endpoints: **{len(summary_data)}**",
              f"- Linked to handler: **{sum(1 for e in summary_data if e['handler_id'])}**",
              "",
              "## Top 15 endpoints by call-tree size",
              "| Method | Path | Tag | Nodes | Files touched | Card |",
              "|--------|------|-----|-------|---------------|------|"]
    for e in top:
        idx_md.append(f"| {e['method']} | `{e['path']}` | {e['tag']} | "
                      f"{e['node_count']} | {len(e['modules_touched'])} | "
                      f"[detail]({e['card_file']}) |")
    idx_md.append("")

    # cross-endpoint reuse hot-list
    reuse_count = Counter()
    for nid, eps in reuse_map.items():
        if len(eps) >= 2:
            reuse_count[nid] = len(eps)
    if reuse_count:
        idx_md.append("## Functions called from 2+ endpoints (top 20)")
        idx_md.append("| Symbol | File:Line | Used by N endpoints |")
        idx_md.append("|--------|-----------|----------------------|")
        for nid, n in reuse_count.most_common(20):
            s = sym_by_id.get(nid)
            if s:
                idx_md.append(f"| `{s['name']}` | `{s['file']}:{s['line']}` | {n} |")
            else:
                idx_md.append(f"| `{nid}` | — | {n} |")

    (out_dir / "endpoints.md").write_text("\n".join(idx_md), encoding="utf-8")

    print(f"\nWrote {out_dir / 'endpoints.json'}", file=sys.stderr)
    print(f"Wrote {out_dir / 'endpoints.md'}", file=sys.stderr)
    print(f"Wrote {len(summary_data)} per-endpoint cards to {endpoints_dir}/",
          file=sys.stderr)
    print(f"\nLinked endpoints: {sum(1 for e in summary_data if e['handler_id'])}/{len(summary_data)}",
          file=sys.stderr)
    print(f"Top reuse: {len([n for n, c in reuse_count.items() if c >= 2])} symbols "
          f"called from 2+ endpoints", file=sys.stderr)


if __name__ == "__main__":
    main()
