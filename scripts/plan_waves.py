#!/usr/bin/env python3
"""
Phase 3: Plan review waves.

Reads segments.json and groups segments into parallel waves of at most
WAVE_SIZE segments each. Foundation segments (no dependencies on other
segments) go in earlier waves so consumers can reference upstream reports.

Outputs wave_plan.json: {"waves": [[seg_name, ...], [seg_name, ...], ...]}
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_WAVE_SIZE = 5


def build_segment_deps(segments, edges):
    """For each segment, which other segments does it depend on?

    A depends on B iff some file in A imports a file in B.
    """
    file_to_seg = {}
    for seg in segments:
        for f in seg["files"]:
            file_to_seg[f] = seg["name"]

    deps = defaultdict(set)
    for src, dst in edges:
        sa, sb = file_to_seg.get(src), file_to_seg.get(dst)
        if sa and sb and sa != sb:
            deps[sa].add(sb)
    return deps


def topological_layers(segments, deps):
    """Kahn's algorithm but yield layers (segments with no remaining deps)
    instead of a flat order. Each layer can run in parallel.
    """
    remaining = {s["name"]: set(deps.get(s["name"], set())) for s in segments}
    layers = []
    seg_by_name = {s["name"]: s for s in segments}

    while remaining:
        ready = [name for name, d in remaining.items() if not d]
        if not ready:
            # cycle — break it by picking the segment with fewest remaining deps
            ready = [min(remaining, key=lambda n: len(remaining[n]))]
        # within a layer, sort by complexity descending so big jobs start first
        ready.sort(key=lambda n: -seg_by_name[n]["complexity_score"])
        layers.append(ready)
        for name in ready:
            remaining.pop(name, None)
        for name in remaining:
            remaining[name] -= set(ready)
    return layers


def chunk_layer(layer, wave_size):
    """Split a wide layer into multiple waves of at most wave_size."""
    return [layer[i : i + wave_size] for i in range(0, len(layer), wave_size)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segments", help="Path to segments.json")
    ap.add_argument("--map", help="Path to project-map.json (for edges)",
                    default=None)
    ap.add_argument("--output", "-o", default=".cartographer/wave_plan.json")
    ap.add_argument("--wave-size", type=int, default=DEFAULT_WAVE_SIZE)
    args = ap.parse_args()

    with open(args.segments) as f:
        seg_data = json.load(f)
    segments = seg_data["segments"]

    edges = []
    if args.map:
        with open(args.map) as f:
            edges = json.load(f).get("edges", [])

    deps = build_segment_deps(segments, edges)
    layers = topological_layers(segments, deps)

    waves = []
    for layer in layers:
        waves.extend(chunk_layer(layer, args.wave_size))

    plan = {
        "wave_size": args.wave_size,
        "total_segments": len(segments),
        "total_waves": len(waves),
        "waves": waves,
        "segment_dependencies": {k: sorted(v) for k, v in deps.items()},
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(plan, f, indent=2)

    print(f"Wrote {out}", file=sys.stderr)
    print(f"\n{len(segments)} segments → {len(waves)} waves "
          f"(max {args.wave_size} per wave)", file=sys.stderr)
    for i, wave in enumerate(waves, 1):
        print(f"  Wave {i}: {wave}", file=sys.stderr)


if __name__ == "__main__":
    main()
