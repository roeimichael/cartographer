#!/usr/bin/env python3
"""
Phase 2: Detect & label functional segments in a codebase.

Reads project-map.json, builds an undirected graph from the file edges, finds
connected components, then labels each component by:
  - dominant integrations (Telegram, Supabase, OpenAI, ...)
  - directory prefix
  - presence of API endpoints

Outputs segments.json (and segments.mmd for visualization).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import networkx as nx  # type: ignore
    HAS_NX = True
except ImportError:
    HAS_NX = False


def build_components(files, edges):
    """Connected components on the undirected import graph."""
    if HAS_NX:
        g = nx.Graph()
        g.add_nodes_from(f["path"] for f in files)
        g.add_edges_from(edges)
        return [list(c) for c in nx.connected_components(g)]

    # stdlib fallback: union-find
    parent = {f["path"]: f["path"] for f in files}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in edges:
        if a in parent and b in parent:
            union(a, b)

    groups = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    return list(groups.values())


def common_dir_prefix(paths):
    if not paths:
        return ""
    parts = [p.split("/") for p in paths]
    common = []
    for i in range(min(len(p) for p in parts)):
        col = {p[i] for p in parts}
        if len(col) == 1:
            common.append(col.pop())
        else:
            break
    return "/".join(common)


# Integrations that are too broad to use as a primary segment label.
# The segmenter still records them, but skips them when picking a name.
LOW_SIGNAL_INTEGRATIONS = {"filesystem", "websocket"}


def label_segment(component_files, file_index, integration_index, endpoints_by_file, idx):
    """Produce a segment record for a connected component."""
    integ_counter = Counter()
    for path in component_files:
        for label in file_index[path].get("integrations", []):
            integ_counter[label] += 1
    top_integ = [label for label, _ in integ_counter.most_common(5)]

    # for naming, ignore low-signal integrations (filesystem, websocket).
    name_integ = [i for i in top_integ if i not in LOW_SIGNAL_INTEGRATIONS]

    seg_endpoints = []
    for path in component_files:
        seg_endpoints.extend(endpoints_by_file.get(path, []))

    prefix = common_dir_prefix(component_files)
    if seg_endpoints:
        name = f"api@{prefix or 'root'}"
    elif name_integ:
        name = name_integ[0]
        if prefix:
            name += f"@{prefix}"
    elif top_integ:
        # only low-signal integrations matched — fall back to directory
        name = prefix if prefix else top_integ[0]
    elif prefix:
        name = prefix
    else:
        name = f"segment_{idx}"
    name = re.sub(r"[^A-Za-z0-9_./@-]", "_", name)[:80]

    # complexity score: files * log(symbols+1) * (1 + integrations)
    file_count = len(component_files)
    symbol_count = sum(file_index[p].get("symbol_count", 0) for p in component_files)
    loc = sum(file_index[p].get("loc", 0) for p in component_files)
    complexity = file_count + symbol_count // 5 + len(top_integ) * 3 + len(seg_endpoints)

    # rough "root files" heuristic: files with the most outgoing edges within the segment
    return {
        "name": name,
        "files": sorted(component_files),
        "file_count": file_count,
        "loc": loc,
        "symbol_count": symbol_count,
        "integrations": top_integ,
        "endpoints": [
            {"method": e["method"], "path": e["path"], "file": e["file"]}
            for e in seg_endpoints
        ],
        "directory_prefix": prefix,
        "complexity_score": complexity,
    }


def split_oversized(segment, max_files=40):
    """If a segment is huge, split it by directory — RECURSIVELY.

    A 200-file segment is too big for one review subagent. Walk down the
    directory tree until each leaf is below max_files. This handles the
    common monolithic backend layout (`src/domains/<X>/`, `src/api/`, etc.)
    where one connected component spans 100+ files but the directory
    structure clearly nominates per-domain boundaries.
    """
    if segment["file_count"] <= max_files:
        return [segment]

    by_subdir = defaultdict(list)
    prefix = segment["directory_prefix"]
    prefix_parts = prefix.split("/") if prefix else []
    for path in segment["files"]:
        parts = path.split("/")
        sub = parts[len(prefix_parts)] if len(parts) > len(prefix_parts) else "_root"
        by_subdir[sub].append(path)

    if len(by_subdir) == 1:
        # can't split further by directory; chunk by file count as last resort
        files = segment["files"]
        result = []
        for i in range(0, len(files), max_files):
            chunk = files[i : i + max_files]
            sub = dict(segment)
            sub["name"] = f"{segment['name']}_part{(i // max_files) + 1}"
            sub["files"] = chunk
            sub["file_count"] = len(chunk)
            result.append(sub)
        return result

    result = []
    for subname, paths in by_subdir.items():
        new = dict(segment)
        new_prefix = "/".join(prefix_parts + [subname]).strip("/")
        new["name"] = f"{segment['name']}/{subname}"
        new["files"] = sorted(paths)
        new["file_count"] = len(paths)
        new["directory_prefix"] = new_prefix
        # recurse — sub-segment may still be oversized
        result.extend(split_oversized(new, max_files))
    return result


def _relabel_segment(seg, file_index, endpoints_by_file):
    """Recompute integrations, endpoints, loc, symbol_count, complexity, and
    name from this segment's actual files (not inherited from parent)."""
    integ_counter = Counter()
    eps = []
    loc = 0
    sym = 0
    for path in seg["files"]:
        f = file_index.get(path, {})
        for label in f.get("integrations", []):
            integ_counter[label] += 1
        eps.extend(endpoints_by_file.get(path, []))
        loc += f.get("loc", 0)
        sym += f.get("symbol_count", 0)
    top_integ = [label for label, _ in integ_counter.most_common(5)]
    name_integ = [i for i in top_integ if i not in LOW_SIGNAL_INTEGRATIONS]

    seg["integrations"] = top_integ
    seg["endpoints"] = [
        {"method": e["method"], "path": e["path"], "file": e["file"]} for e in eps
    ]
    seg["loc"] = loc
    seg["symbol_count"] = sym
    seg["complexity_score"] = (seg["file_count"] + sym // 5
                               + len(top_integ) * 3 + len(eps))

    # If the original auto-name encodes a stale integration (because parent's
    # integration set was used), re-derive name from current data.
    prefix = seg.get("directory_prefix", "")
    # Strip parent's leading "<integ>@" if it's no longer the dominant integration
    if "@" in seg["name"]:
        existing_integ, _, rest = seg["name"].partition("@")
        if existing_integ not in name_integ and rest:
            # rebuild name from this segment's own data
            if eps:
                seg["name"] = f"api@{prefix or rest}"
            elif name_integ:
                seg["name"] = f"{name_integ[0]}@{prefix or rest}"
            elif prefix:
                seg["name"] = prefix
            else:
                seg["name"] = rest


def _consolidate_to_domain(segments, file_index, endpoints_by_file,
                            max_files, min_files, max_overflow):
    """Merge tiny segments into the nearest related segment of the same domain.

    "Domain" here = first 2-3 path components (e.g. `src/domains/watchlists/`).
    A 1-file `src/domains/strategies/api.py` segment merges into a sibling
    `src/domains/strategies/crafter/` segment, producing one logical
    `strategies` segment.

    Constraints:
      - Only merge if both segments share a domain prefix.
      - Resulting segment must not exceed max_files * max_overflow.
      - Don't merge across very different integration sets (e.g. don't fold
        an auth file into a market_data segment even if they share a parent).

    This pass shrinks segment count dramatically on monolithic projects
    where the connected-components algorithm couldn't separate domains.
    """
    if min_files <= 1:
        return segments

    hard_cap = int(max_files * max_overflow)

    def domain_key(seg, depth=3):
        """Pick the (depth)-deep directory prefix as the domain key."""
        prefix = seg.get("directory_prefix", "")
        if not prefix:
            # fall back to first file's first 2-3 path parts
            if not seg["files"]:
                return None
            parts = seg["files"][0].split("/")
            return "/".join(parts[:depth]) if len(parts) >= 2 else parts[0]
        parts = prefix.split("/")
        return "/".join(parts[:depth]) if len(parts) >= 2 else prefix

    def integ_compatible(a, b):
        """Two segments are mergeable if their integration sets aren't
        disjoint, OR if at least one of them is integration-blank."""
        ai = set(a.get("integrations", []))
        bi = set(b.get("integrations", []))
        if not ai or not bi:
            return True
        # consider them compatible if any non-low-signal integration overlaps
        ai_strong = ai - LOW_SIGNAL_INTEGRATIONS
        bi_strong = bi - LOW_SIGNAL_INTEGRATIONS
        if not ai_strong or not bi_strong:
            return True
        return bool(ai_strong & bi_strong)

    # Index segments by domain key
    by_domain = defaultdict(list)
    for seg in segments:
        k = domain_key(seg)
        by_domain[k].append(seg)

    # For each tiny segment, try to merge into the largest sibling under the
    # same domain key, then re-derive metadata.
    merged = []
    consumed = set()
    for seg in segments:
        if id(seg) in consumed:
            continue
        if seg["file_count"] >= min_files:
            merged.append(seg)
            continue

        k = domain_key(seg)
        siblings = [s for s in by_domain.get(k, [])
                   if id(s) != id(seg) and id(s) not in consumed
                   and integ_compatible(seg, s)]
        if not siblings:
            # try a broader domain (depth 2 instead of 3)
            broad_k = "/".join((domain_key(seg, depth=2) or "").split("/")[:2])
            siblings = [s for s in segments
                       if id(s) != id(seg) and id(s) not in consumed
                       and (domain_key(s, depth=2) or "").startswith(broad_k or "_")
                       and integ_compatible(seg, s)]
        if not siblings:
            merged.append(seg)
            continue

        # pick largest sibling under the cap
        siblings.sort(key=lambda s: -s["file_count"])
        target = None
        for sib in siblings:
            if sib["file_count"] + seg["file_count"] <= hard_cap:
                target = sib
                break
        if not target:
            merged.append(seg)
            continue

        # merge seg into target
        new_files = sorted(set(target["files"]) | set(seg["files"]))
        target["files"] = new_files
        target["file_count"] = len(new_files)
        consumed.add(id(seg))
        # rename target to a domain-shaped name if it's now broader than its
        # original directory_prefix
        common = common_dir_prefix(new_files)
        target["directory_prefix"] = common
        _relabel_segment(target, file_index, endpoints_by_file)

    # Drop consumed (already added through their target)
    final = [s for s in merged if id(s) not in consumed]

    # Final pass: merge leftover tiny orphans by their directory_prefix.
    # Many test_*.py, scripts/foo.py, etc. end up as 1-file segments because
    # they have no internal callees; group them by top-level dir into one
    # "<dir>-misc" segment so they get one review instead of N.
    return _bundle_singletons_by_top_dir(final, file_index, endpoints_by_file,
                                          min_files=min_files,
                                          max_files=int(max_files * max_overflow))


def _bundle_singletons_by_top_dir(segments, file_index, endpoints_by_file,
                                    min_files, max_files):
    """Group segments still smaller than min_files by their top-level dir.
    e.g. all 1-file `tests/test_*.py` segments → one `tests-misc` segment."""
    big = [s for s in segments if s["file_count"] >= min_files]
    small = [s for s in segments if s["file_count"] < min_files]
    if not small:
        return big

    by_top = defaultdict(list)
    standalone = []
    for s in small:
        prefix = s.get("directory_prefix", "")
        if not prefix:
            # singleton at root — just keep
            standalone.append(s)
            continue
        top = prefix.split("/")[0]
        by_top[top].append(s)

    bundles = []
    for top, group in by_top.items():
        if len(group) <= 1:
            standalone.extend(group)
            continue
        # one bundle per top-dir — but split if it would exceed max_files
        files = []
        for g in group:
            files.extend(g["files"])
        files = sorted(set(files))
        if len(files) <= max_files:
            new = {
                "name": f"{top}-misc",
                "files": files,
                "file_count": len(files),
                "directory_prefix": top,
                "loc": 0,
                "symbol_count": 0,
                "integrations": [],
                "endpoints": [],
                "complexity_score": 0,
            }
            _relabel_segment(new, file_index, endpoints_by_file)
            bundles.append(new)
        else:
            # too many — split into chunks of max_files
            for i in range(0, len(files), max_files):
                chunk = files[i : i + max_files]
                new = {
                    "name": f"{top}-misc-part{i // max_files + 1}",
                    "files": chunk,
                    "file_count": len(chunk),
                    "directory_prefix": top,
                    "loc": 0,
                    "symbol_count": 0,
                    "integrations": [],
                    "endpoints": [],
                    "complexity_score": 0,
                }
                _relabel_segment(new, file_index, endpoints_by_file)
                bundles.append(new)

    return big + bundles + standalone


def _merge_sibling_segments(segments, max_files):
    """Merge segments that share the same dominant integration AND the same
    parent directory. E.g. ['react@frontend/src/components',
    'react@frontend/src/hooks', 'react@frontend/src/pages'] all share parent
    'frontend/src' and integration 'react' — merge into 'react@frontend/src'.

    Skip merges that would exceed max_files (oversized segments are bad too).
    """
    # group by (top_integration_or_blank, parent_dir_2_levels_up)
    groups = defaultdict(list)
    standalone = []
    for seg in segments:
        prefix = seg.get("directory_prefix", "")
        # we want to group at "frontend/src" level — 2 path components in
        if not prefix or "/" not in prefix:
            standalone.append(seg)
            continue
        parts = prefix.split("/")
        # parent at 2 levels deep (e.g. "frontend/src" from "frontend/src/components")
        if len(parts) >= 3:
            parent = "/".join(parts[:2])
        else:
            standalone.append(seg)
            continue
        top_integ = seg["integrations"][0] if seg["integrations"] else ""
        # only merge if integration is present AND not low-signal
        if top_integ and top_integ not in LOW_SIGNAL_INTEGRATIONS:
            groups[(top_integ, parent)].append(seg)
        else:
            standalone.append(seg)

    merged = list(standalone)
    for (integ, parent), group in groups.items():
        if len(group) <= 1:
            merged.extend(group)
            continue
        total_files = sum(s["file_count"] for s in group)
        if total_files > max_files:
            # too big to merge — keep separate
            merged.extend(group)
            continue
        # build merged segment
        all_files = sorted({f for s in group for f in s["files"]})
        all_endpoints = []
        for s in group:
            all_endpoints.extend(s.get("endpoints", []))
        all_integ = list({i for s in group for i in s["integrations"]})
        loc = sum(s.get("loc", 0) for s in group)
        sym = sum(s.get("symbol_count", 0) for s in group)
        complexity = (len(all_files) + sym // 5
                      + len(all_integ) * 3 + len(all_endpoints))
        merged.append({
            "name": f"{integ}@{parent}",
            "files": all_files,
            "file_count": len(all_files),
            "loc": loc,
            "symbol_count": sym,
            "integrations": sorted(all_integ),
            "endpoints": all_endpoints,
            "directory_prefix": parent,
            "complexity_score": complexity,
        })
    return merged


def render_mermaid(segments):
    lines = ["graph TB"]
    for i, seg in enumerate(segments):
        sid = f"S{i}"
        integ = ",".join(seg["integrations"]) or "—"
        lines.append(f'  {sid}["{seg["name"]}<br/>{seg["file_count"]} files · {integ}"]')
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_map", help="Path to project-map.json")
    ap.add_argument("--output", "-o", default=".cartographer/segments.json")
    ap.add_argument("--max-files-per-segment", type=int, default=40,
                    help="Soft cap — split segments larger than this")
    ap.add_argument("--min-files-per-segment", type=int, default=3,
                    help="Segments smaller than this are merge candidates "
                         "(folded into the nearest related segment)")
    ap.add_argument("--max-overflow", type=float, default=1.5,
                    help="Merging may exceed max-files by up to this factor "
                         "(default 1.5x). Higher = fewer/bigger segments.")
    args = ap.parse_args()

    with open(args.project_map) as f:
        pmap = json.load(f)

    file_index = {f["path"]: f for f in pmap["files"]}
    endpoints_by_file = defaultdict(list)
    for ep in pmap.get("endpoints", []):
        endpoints_by_file[ep["file"]].append(ep)

    # filter near-empty files (e.g. __init__.py with <= 3 LOC) — they're
    # package markers, not segments. Keep them indexed but exclude from
    # graph construction so they don't anchor singleton components.
    def is_trivial(f):
        path = f["path"]
        loc = f.get("loc", 0)
        # __init__.py with ≤3 LOC, OR config.py with ≤10 LOC (mostly constants/wiring)
        if path.endswith("__init__.py") and loc <= 3:
            return True
        if path.endswith(("/config.py", "\\config.py")) and loc <= 12:
            return True
        return False

    indexed_files = [f for f in pmap["files"] if not is_trivial(f)]
    trivial_paths = {f["path"] for f in pmap["files"] if is_trivial(f)}
    edges_filtered = [(a, b) for a, b in pmap["edges"]
                      if a not in trivial_paths and b not in trivial_paths]

    components = build_components(indexed_files, edges_filtered)

    edge_nodes = set()
    for a, b in edges_filtered:
        edge_nodes.add(a); edge_nodes.add(b)
    orphans = [f["path"] for f in indexed_files if f["path"] not in edge_nodes]
    components.extend([[o] for o in orphans])

    # Merge orphan singletons by directory prefix (one level up from file).
    # This collapses fragmented frontend/* segments that the import resolver
    # couldn't connect (e.g. via aliases that didn't resolve).
    by_dir = defaultdict(list)
    pure_orphans = []
    for comp in components:
        if len(comp) == 1:
            d = os.path.dirname(comp[0]) or "_root"
            by_dir[d].append(comp[0])
        else:
            pure_orphans.append(comp)
    merged_orphans = [files for files in by_dir.values()]
    components = pure_orphans + merged_orphans

    segments = []
    for i, comp in enumerate(sorted(components, key=len, reverse=True)):
        seg = label_segment(comp, file_index, pmap.get("integration_index", {}),
                            endpoints_by_file, i)
        segments.extend(split_oversized(seg, max_files=args.max_files_per_segment))

    # Re-derive each segment's integrations + endpoints + complexity from its
    # actual files (sub-segments shouldn't inherit parent's integration set).
    for seg in segments:
        _relabel_segment(seg, file_index, endpoints_by_file)

    # Post-pass: merge sibling segments under the same directory ancestor.
    segments = _merge_sibling_segments(segments, args.max_files_per_segment)

    # Domain-consolidation: a "watchlist" segment should cover create/delete/
    # modify/etc. — not split into 5 single-file segments per file. After
    # the splitter ran, fold small singletons (≤ args.min_files_per_segment)
    # into the nearest related segment. This gives reviewers a domain-shaped
    # view instead of one-segment-per-file noise.
    segments = _consolidate_to_domain(segments, file_index, endpoints_by_file,
                                       max_files=args.max_files_per_segment,
                                       min_files=args.min_files_per_segment,
                                       max_overflow=args.max_overflow)

    # sort by complexity descending
    segments.sort(key=lambda s: -s["complexity_score"])

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"segments": segments}, f, indent=2)

    mmd = out.parent / (out.stem + ".mmd")
    with open(mmd, "w") as f:
        f.write(render_mermaid(segments))

    print(f"Wrote {out} ({len(segments)} segments)", file=sys.stderr)
    print(f"Wrote {mmd}", file=sys.stderr)
    print("\nTop 10 segments by complexity:", file=sys.stderr)
    for s in segments[:10]:
        print(f"  {s['complexity_score']:>4}  {s['name']:<40}  "
              f"{s['file_count']} files, integrations: {s['integrations']}", file=sys.stderr)


if __name__ == "__main__":
    main()
