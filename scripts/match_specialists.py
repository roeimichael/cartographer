#!/usr/bin/env python3
"""
Phase 3.5: Match a specialist agent to each segment.

Reads wave_plan.json + segments.json + agents/*.md, and writes an enriched
wave plan where every segment has an `assigned_agent` field.

Specialist files use YAML-ish frontmatter:

    ---
    name: backend-api-reviewer
    triggers:
      integrations: [fastapi, flask]
      file_patterns: ["**/routes/**"]
      endpoint_count_min: 1
    priority: 80
    ---

Scoring per (segment, specialist):
    score = priority * (
        50 * |integration overlap|
      + 10 * (# files in segment matching any file_pattern)
      +  5 * (1 if endpoint_count_min met else 0)
    )

Highest score wins. Tie at zero → generalist-reviewer.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(text):
    """Tiny YAML-ish parser — enough for our flat frontmatter shape.

    We avoid a PyYAML dep so the skill stays zero-install. Supports:
      key: value
      key: [a, b, c]
      key:
        subkey: value
        sublist: [a, b]
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    body = m.group(1)
    out = {}
    current_section = None
    for raw in body.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indented = raw.startswith(" ") or raw.startswith("\t")
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        target = out
        if indented and current_section is not None:
            target = out[current_section]
        if val == "":
            out[key] = {}
            current_section = key
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            target[key] = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
        else:
            v = val.strip('"').strip("'")
            try:
                target[key] = int(v)
            except ValueError:
                target[key] = v
        if not indented:
            current_section = None
    return out


def load_specialists(agents_dir):
    specialists = []
    for p in sorted(Path(agents_dir).glob("*.md")):
        if p.name == "AGENTS.md":
            continue
        text = p.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm or "name" not in fm:
            continue
        triggers = fm.get("triggers", {}) or {}
        specialists.append({
            "name": fm["name"],
            "file": p.name,
            "priority": int(fm.get("priority", 0)),
            "integrations": [s.lower() for s in triggers.get("integrations", []) or []],
            "file_patterns": triggers.get("file_patterns", []) or [],
            "endpoint_count_min": int(triggers.get("endpoint_count_min", 0) or 0),
        })
    return specialists


def score_match(segment, specialist):
    seg_ints = {i.lower() for i in segment.get("integrations", [])}
    spec_ints = set(specialist["integrations"])
    overlap = len(seg_ints & spec_ints)

    file_hits = 0
    for f in segment.get("files", []):
        for pat in specialist["file_patterns"]:
            if fnmatch.fnmatch(f, pat) or fnmatch.fnmatch(f, pat.replace("**/", "")):
                file_hits += 1
                break

    endpoint_bonus = 0
    if specialist["endpoint_count_min"] > 0:
        if len(segment.get("endpoints", [])) >= specialist["endpoint_count_min"]:
            endpoint_bonus = 1

    raw = 50 * overlap + 10 * file_hits + 5 * endpoint_bonus
    return raw * max(specialist["priority"], 1)


def assign(segment, specialists):
    scored = [(score_match(segment, s), s) for s in specialists]
    scored.sort(key=lambda x: (-x[0], -x[1]["priority"]))
    best_score, best = scored[0]
    if best_score <= 0:
        for s in specialists:
            if s["name"] == "generalist-reviewer":
                return s["name"], 0, []
        return best["name"], 0, []
    runners_up = [
        {"name": s["name"], "score": sc}
        for sc, s in scored[1:4] if sc > 0
    ]
    return best["name"], best_score, runners_up


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wave_plan", help="Path to wave_plan.json")
    ap.add_argument("--segments", required=True, help="Path to segments.json")
    ap.add_argument("--agents-dir", default="agents", help="Path to agents/ directory")
    ap.add_argument("--output", "-o", default=None,
                    help="Output path (default: overwrite input wave_plan)")
    ap.add_argument("--gap-threshold", type=int, default=1500,
                    help="Score below which a segment is flagged as a "
                         "specialist-coverage gap (segment will fall back "
                         "to generalist-reviewer unless user intervenes).")
    ap.add_argument("--gaps-output", default=None,
                    help="Path to write specialist_gaps.json (default: "
                         "alongside wave_plan)")
    args = ap.parse_args()

    plan = json.loads(Path(args.wave_plan).read_text(encoding="utf-8"))
    segs = json.loads(Path(args.segments).read_text(encoding="utf-8"))["segments"]
    seg_by_name = {s["name"]: s for s in segs}

    specialists = load_specialists(args.agents_dir)
    if not specialists:
        print(f"No specialists found in {args.agents_dir}", file=sys.stderr)
        sys.exit(1)

    assignments = {}
    for wave in plan["waves"]:
        for seg_name in wave:
            seg = seg_by_name.get(seg_name)
            if not seg:
                continue
            agent, score, runners_up = assign(seg, specialists)
            assignments[seg_name] = {
                "assigned_agent": agent,
                "score": score,
                "runners_up": runners_up,
            }

    plan["specialist_assignments"] = assignments
    plan["specialist_index"] = {s["name"]: s["file"] for s in specialists}

    # Coverage-gap detection: flag segments whose top match scored low or
    # fell back to generalist on a non-trivial segment.
    gaps = []
    for seg_name, info in assignments.items():
        seg = seg_by_name.get(seg_name, {})
        # gap criteria:
        #   - score below threshold AND segment has > 2 files (singletons aren't worth flagging)
        #   - OR fell back to generalist on a segment with > 5 files
        is_gap = False
        reason = ""
        if info["score"] < args.gap_threshold and seg.get("file_count", 0) > 2:
            is_gap = True
            reason = f"low score ({info['score']}) — no specialist matched well"
        elif info["assigned_agent"] == "generalist-reviewer" and seg.get("file_count", 0) > 5:
            is_gap = True
            reason = "fell back to generalist on a non-trivial segment"
        if is_gap:
            gaps.append({
                "segment": seg_name,
                "file_count": seg.get("file_count", 0),
                "integrations": seg.get("integrations", []),
                "directory_prefix": seg.get("directory_prefix", ""),
                "assigned_agent": info["assigned_agent"],
                "score": info["score"],
                "reason": reason,
                "runners_up": info.get("runners_up", []),
            })

    plan["specialist_gaps"] = gaps

    out = Path(args.output or args.wave_plan)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    if gaps:
        gaps_path = Path(args.gaps_output) if args.gaps_output else (out.parent / "specialist_gaps.json")
        gaps_path.write_text(
            json.dumps({"gaps": gaps,
                         "threshold": args.gap_threshold,
                         "stats": {"count": len(gaps),
                                    "total_segments": len(assignments)}},
                        indent=2),
            encoding="utf-8",
        )
        print(f"\nSpecialist coverage gaps: {len(gaps)} segment(s) need attention",
              file=sys.stderr)
        print(f"  → {gaps_path}", file=sys.stderr)
        for g in gaps[:8]:
            print(f"    - {g['segment']:40s}  ({g['file_count']}f) "
                  f"score={g['score']}  reason: {g['reason']}", file=sys.stderr)

    print(f"Wrote {out}", file=sys.stderr)
    print(f"\nAssignments:", file=sys.stderr)
    for seg, info in assignments.items():
        ru = ", ".join(f"{r['name']}({r['score']})" for r in info["runners_up"])
        print(f"  {seg:40s} → {info['assigned_agent']:30s} score={info['score']}"
              + (f"   alts: {ru}" if ru else ""),
              file=sys.stderr)


if __name__ == "__main__":
    main()
