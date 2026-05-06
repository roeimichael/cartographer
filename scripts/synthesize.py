#!/usr/bin/env python3
"""
Phase 5: Cross-segment synthesis.

Reads:
  - .cartographer/reports/<segment>.md  — per-segment review reports (subagent output)
  - .cartographer/project-map.json      — symbol & integration data

Detects:
  - Duplicate / near-duplicate function names across segments (fuzzy match)
  - Identical signatures across segments (likely refactor candidates)
  - Naming convention drift (snake_case vs camelCase ratio per segment)
  - Centralization candidates (patterns appearing in 3+ segments: SQL helpers,
    enums, validators, error wrappers)
  - Style fingerprint outliers (avg fn length, comment density)

Outputs:
  - synthesis.json — structured findings
  - synthesis.md   — human-readable summary

The per-segment reports must follow the schema in prompts/segment_review.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev

try:
    from rapidfuzz import fuzz  # type: ignore
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False


# ---------- report parsing ----------

SECTION_RE_TEMPLATE = r"^##\s+{}\s*\n(.*?)(?=^##\s+(?:{})\s*\n|\Z)"
FILES_RE = re.compile(r"^-\s+`([^`]+)`", re.M)
SPECIALIST_RE = re.compile(r"\*\*Reviewed by:\*\*\s*([\w-]+)")


def _extract_files_section(text: str) -> list:
    """Pull file list bullets following '## Files reviewed'."""
    m = re.search(r"^##\s+Files reviewed\s*\n(.+?)(?=^##\s|\Z)",
                  text, re.M | re.DOTALL)
    if not m:
        # fallback: any backtick paths in the doc (older schemas)
        return [f for f in FILES_RE.findall(text) if "/" in f or "." in f]
    return [f for f in FILES_RE.findall(m.group(1)) if f]


def _extract_specialist(text: str) -> str:
    m = SPECIALIST_RE.search(text)
    return m.group(1) if m else ""


def _extract_section(text: str, heading: str, terminators: list = None) -> str:
    """Extract the body of `## <heading>` until ANY next `## ` heading
    (or end of file). The terminators arg is kept for back-compat but
    ignored — we just stop at the next h2."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)",
        re.M | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _extract_refactor_items(refactor_section: str) -> list:
    """Best-effort: split a 'Refactor suggestions' section into items.

    Reports vary — some use bullet lists, some use numbered, some use sub-h3.
    We grab anything that looks like a separable item.
    """
    if not refactor_section:
        return []
    items = []
    # Split on lines starting with `-`, `*`, `1.`, `### `
    chunks = re.split(r"\n(?=^(?:-|\*|\d+\.|\#\#\#)\s+)", refactor_section, flags=re.M)
    for chunk in chunks:
        line = chunk.strip()
        if not line or len(line) < 8:
            continue
        # strip leading list markers
        line = re.sub(r"^(?:-|\*|\d+\.|\#\#\#)\s+", "", line)
        items.append(line[:500])  # cap to keep synthesis.json readable
    return items[:10]  # max 10 per segment


def _extract_concerns_items(concerns_section: str) -> list:
    if not concerns_section:
        return []
    items = []
    for line in concerns_section.splitlines():
        line = line.strip()
        if line.startswith(("-", "*")) or re.match(r"^\d+\.", line):
            line = re.sub(r"^(?:-|\*|\d+\.)\s+", "", line)
            if line:
                items.append(line[:300])
    return items[:8]


# ---------- name similarity ----------

def name_similarity(a: str, b: str) -> int:
    if HAS_FUZZ:
        return int(fuzz.ratio(a.lower(), b.lower()))
    # stdlib fallback: SequenceMatcher
    from difflib import SequenceMatcher
    return int(SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100)


def normalize_name(n: str) -> str:
    """For matching: strip common prefixes/suffixes and convert to snake."""
    n = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", n).lower()
    n = re.sub(r"^(get|set|fetch|load|create|make|build|do|handle|process)_", "", n)
    n = re.sub(r"_(handler|fn|func|impl|inner|helper)$", "", n)
    return n


# ---------- naming convention ----------

CAMEL_RE = re.compile(r"^[a-z][a-zA-Z0-9]*[A-Z]")
SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PASCAL_RE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")


def naming_style(name: str) -> str:
    if "_" in name and SNAKE_RE.match(name):
        return "snake"
    if CAMEL_RE.match(name):
        return "camel"
    if PASCAL_RE.match(name):
        return "pascal"
    return "other"


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports_dir", help="Directory containing <segment>.md reports")
    ap.add_argument("--map", required=True, help="Path to project-map.json")
    ap.add_argument("--output", "-o", default=".cartographer/synthesis.json")
    ap.add_argument("--name-threshold", type=int, default=82,
                    help="Fuzzy match threshold for duplicate function names")
    args = ap.parse_args()

    with open(args.map) as f:
        pmap = json.load(f)

    # ---- gather symbols per file from project-map ----
    file_to_symbols = defaultdict(list)
    for s in pmap["symbols"]:
        file_to_symbols[s["file"]].append(s)

    # ---- determine segment membership from per-segment markdown reports ----
    # Also extract the prose findings the agents wrote (concerns, refactors,
    # cross-segment hints, specialist findings) so the synthesizer can roll
    # them up instead of ignoring agent output.
    reports_dir = Path(args.reports_dir)
    segments = {}
    for rp in sorted(reports_dir.glob("*.md")):
        seg_name = rp.stem
        text = rp.read_text(encoding="utf-8", errors="replace")
        files = _extract_files_section(text)
        segments[seg_name] = {
            "files": files,
            "report": text,
            "specialist": _extract_specialist(text),
            "concerns": _extract_section(text, "Concerns / smells",
                                          ["Refactor suggestions"]),
            "refactors": _extract_section(text, "Refactor suggestions",
                                           ["Coverage notes", "End", "$"]),
            "cross_hints": _extract_section(text, "Cross-segment hints",
                                             ["Specialist findings",
                                              "Concerns / smells"]),
            "specialist_findings": _extract_section(text, "Specialist findings",
                                                     ["Concerns / smells"]),
            "conventions": _extract_section(text, "Conventions observed",
                                             ["Internal duplication",
                                              "Cross-segment hints"]),
        }

    # if reports are missing, fall back to segments.json next to project-map
    if not segments:
        segs_path = Path(args.map).parent / "segments.json"
        if segs_path.exists():
            print("No reports found; falling back to segments.json", file=sys.stderr)
            with open(segs_path) as f:
                for seg in json.load(f)["segments"]:
                    segments[seg["name"]] = {"files": seg["files"], "report": ""}

    # ---- build segment -> symbols ----
    seg_symbols = {}
    for name, data in segments.items():
        symbols = []
        for f in data["files"]:
            symbols.extend(file_to_symbols.get(f, []))
        seg_symbols[name] = symbols

    # ---- finding 1: duplicate function names across segments ----
    duplicates = []
    seg_names = list(seg_symbols.keys())
    for i in range(len(seg_names)):
        for j in range(i + 1, len(seg_names)):
            a, b = seg_names[i], seg_names[j]
            for sa in seg_symbols[a]:
                if sa["kind"] != "function":
                    continue
                for sb in seg_symbols[b]:
                    if sb["kind"] != "function":
                        continue
                    if normalize_name(sa["name"]) == normalize_name(sb["name"]):
                        duplicates.append({
                            "kind": "exact_normalized_match",
                            "name_a": sa["name"], "name_b": sb["name"],
                            "file_a": sa["file"], "file_b": sb["file"],
                            "segment_a": a, "segment_b": b,
                            "score": 100,
                        })
                    elif name_similarity(sa["name"], sb["name"]) >= args.name_threshold:
                        if sa["name"].lower() != sb["name"].lower():
                            duplicates.append({
                                "kind": "fuzzy_match",
                                "name_a": sa["name"], "name_b": sb["name"],
                                "file_a": sa["file"], "file_b": sb["file"],
                                "segment_a": a, "segment_b": b,
                                "score": name_similarity(sa["name"], sb["name"]),
                            })

    # ---- finding 2: naming convention drift per segment ----
    style_per_segment = {}
    for name, syms in seg_symbols.items():
        if not syms:
            continue
        styles = Counter()
        for s in syms:
            if s["kind"] == "function":
                styles[naming_style(s["name"])] += 1
        if not styles:
            continue
        total = sum(styles.values())
        dominant = styles.most_common(1)[0][0]
        purity = styles[dominant] / total
        style_per_segment[name] = {
            "dominant": dominant,
            "purity": round(purity, 3),
            "distribution": dict(styles),
            "function_count": total,
        }

    # find drift: segments whose dominant style differs from project-wide majority
    project_styles = Counter()
    for s in style_per_segment.values():
        project_styles[s["dominant"]] += 1
    if project_styles:
        project_dominant = project_styles.most_common(1)[0][0]
        naming_outliers = [
            {"segment": n, **s}
            for n, s in style_per_segment.items()
            if s["dominant"] != project_dominant or s["purity"] < 0.85
        ]
    else:
        project_dominant = None
        naming_outliers = []

    # ---- finding 3: centralization candidates (patterns in 3+ segments) ----
    # heuristic: function names matching common helper patterns
    patterns = {
        "sql_helpers":   re.compile(r"^(?:run|exec|execute|query)_?(?:sql|query|stmt)", re.I),
        "validators":    re.compile(r"^(?:validate|is_valid|check)_", re.I),
        "error_wrappers":re.compile(r"^(?:wrap|handle|format)_?error", re.I),
        "id_generators": re.compile(r"^(?:gen|generate|make|new)_?(?:id|uuid|token)", re.I),
        "date_helpers":  re.compile(r"^(?:format|parse|to)_?(?:date|time|timestamp)", re.I),
        "loggers":       re.compile(r"^(?:log|trace|emit)_", re.I),
    }
    centralization = []
    for label, pat in patterns.items():
        hits = defaultdict(list)  # segment -> [symbols]
        for seg, syms in seg_symbols.items():
            for s in syms:
                if s["kind"] == "function" and pat.search(s["name"]):
                    hits[seg].append(s)
        if len(hits) >= 3:
            centralization.append({
                "pattern": label,
                "segments_affected": sorted(hits.keys()),
                "occurrences": sum(len(v) for v in hits.values()),
                "examples": [
                    {"segment": seg, "name": s["name"], "file": s["file"]}
                    for seg, syms in list(hits.items())[:5]
                    for s in syms[:2]
                ],
            })

    # ---- finding 4: style fingerprint (LOC / fn count, etc.) ----
    fingerprints = {}
    for name, data in segments.items():
        files_meta = [f for f in pmap["files"] if f["path"] in data["files"]]
        if not files_meta:
            continue
        total_loc = sum(f["loc"] for f in files_meta)
        total_syms = sum(f["symbol_count"] for f in files_meta)
        avg_loc_per_symbol = (total_loc / total_syms) if total_syms else 0
        fingerprints[name] = {
            "files": len(files_meta),
            "loc": total_loc,
            "symbols": total_syms,
            "avg_loc_per_symbol": round(avg_loc_per_symbol, 1),
        }
    # outliers: avg_loc_per_symbol > 2 stdev from mean
    style_outliers = []
    if len(fingerprints) >= 3:
        avgs = [f["avg_loc_per_symbol"] for f in fingerprints.values() if f["avg_loc_per_symbol"]]
        if len(avgs) >= 2:
            mu, sigma = mean(avgs), stdev(avgs)
            for name, fp in fingerprints.items():
                if sigma and abs(fp["avg_loc_per_symbol"] - mu) > 2 * sigma:
                    style_outliers.append({
                        "segment": name,
                        "avg_loc_per_symbol": fp["avg_loc_per_symbol"],
                        "project_mean": round(mu, 1),
                        "project_stdev": round(sigma, 1),
                    })

    # ---- finding 5: aggregate per-segment refactor suggestions + concerns ----
    # This is the missing-piece fix: the agents WROTE concrete findings,
    # we just weren't reading them. Now we do.
    aggregated_refactors = []
    aggregated_concerns = []
    aggregated_cross_hints = []
    for seg_name, data in segments.items():
        for item in _extract_refactor_items(data.get("refactors", "")):
            aggregated_refactors.append({
                "segment": seg_name,
                "specialist": data.get("specialist", ""),
                "text": item,
            })
        for item in _extract_concerns_items(data.get("concerns", "")):
            aggregated_concerns.append({
                "segment": seg_name,
                "specialist": data.get("specialist", ""),
                "text": item,
            })
        # cross-hints: keep as paragraph(s) per segment
        ch = data.get("cross_hints", "").strip()
        if ch and ch.lower() != "none observed.":
            aggregated_cross_hints.append({
                "segment": seg_name,
                "specialist": data.get("specialist", ""),
                "text": ch[:1000],
            })

    # ---- assemble synthesis ----
    synth = {
        "summary": {
            "segments_reviewed": len(segments),
            "duplicate_name_pairs": len(duplicates),
            "naming_outlier_segments": len(naming_outliers),
            "centralization_candidates": len(centralization),
            "style_outlier_segments": len(style_outliers),
            "project_naming_convention": project_dominant,
            "agent_refactor_items": len(aggregated_refactors),
            "agent_concerns": len(aggregated_concerns),
            "agent_cross_hints": len(aggregated_cross_hints),
        },
        "duplicates": sorted(duplicates, key=lambda d: -d["score"]),
        "naming_outliers": naming_outliers,
        "centralization_candidates": centralization,
        "style_outliers": style_outliers,
        "fingerprints": fingerprints,
        "agent_findings": {
            "refactor_suggestions": aggregated_refactors,
            "concerns": aggregated_concerns,
            "cross_segment_hints": aggregated_cross_hints,
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(synth, f, indent=2)

    md_path = out.with_suffix(".md")
    with open(md_path, "w") as f:
        f.write(render_markdown(synth))

    print(f"Wrote {out}", file=sys.stderr)
    print(f"Wrote {md_path}", file=sys.stderr)
    s = synth["summary"]
    print(f"\n{s['segments_reviewed']} segments synthesized:", file=sys.stderr)
    print(f"  {s['duplicate_name_pairs']} duplicate name pairs", file=sys.stderr)
    print(f"  {s['naming_outlier_segments']} naming-convention outlier segments", file=sys.stderr)
    print(f"  {s['centralization_candidates']} centralization candidates", file=sys.stderr)
    print(f"  {s['style_outlier_segments']} style-fingerprint outliers", file=sys.stderr)


def render_markdown(synth) -> str:
    lines = ["# Cross-segment synthesis", ""]
    s = synth["summary"]
    lines.append(f"- Segments reviewed: **{s['segments_reviewed']}**")
    lines.append(f"- Project naming convention: **{s['project_naming_convention']}**")
    lines.append(f"- Duplicate name pairs: **{s['duplicate_name_pairs']}**")
    lines.append(f"- Naming-convention outlier segments: **{s['naming_outlier_segments']}**")
    lines.append(f"- Centralization candidates: **{s['centralization_candidates']}**")
    lines.append(f"- Style fingerprint outliers: **{s['style_outlier_segments']}**")
    lines.append("")

    if synth["duplicates"]:
        lines.append("## Duplicate / near-duplicate functions")
        for d in synth["duplicates"][:30]:
            lines.append(
                f"- `{d['name_a']}` in `{d['file_a']}` ({d['segment_a']})  ↔  "
                f"`{d['name_b']}` in `{d['file_b']}` ({d['segment_b']})  — score {d['score']}"
            )
        if len(synth["duplicates"]) > 30:
            lines.append(f"- *... {len(synth['duplicates']) - 30} more in synthesis.json*")
        lines.append("")

    if synth["centralization_candidates"]:
        lines.append("## Centralization candidates")
        for c in synth["centralization_candidates"]:
            lines.append(f"### {c['pattern']}")
            lines.append(f"Appears in {len(c['segments_affected'])} segments, "
                         f"{c['occurrences']} occurrences total.")
            lines.append("Examples:")
            for ex in c["examples"]:
                lines.append(f"- `{ex['name']}` ({ex['segment']}) — `{ex['file']}`")
            lines.append("")

    if synth["naming_outliers"]:
        lines.append("## Naming convention outliers")
        for o in synth["naming_outliers"]:
            lines.append(f"- **{o['segment']}**: dominant `{o['dominant']}` "
                         f"(purity {o['purity']}), distribution {o['distribution']}")
        lines.append("")

    if synth["style_outliers"]:
        lines.append("## Style fingerprint outliers")
        for o in synth["style_outliers"]:
            lines.append(f"- **{o['segment']}**: {o['avg_loc_per_symbol']} LOC/symbol "
                         f"(project mean {o['project_mean']} ± {o['project_stdev']})")
        lines.append("")

    af = synth.get("agent_findings", {})
    if af.get("refactor_suggestions"):
        lines.append("## Refactor backlog (aggregated from per-segment reports)")
        lines.append(f"_{len(af['refactor_suggestions'])} items across "
                     f"{len(set(r['segment'] for r in af['refactor_suggestions']))} segments._")
        lines.append("")
        for r in af["refactor_suggestions"][:50]:
            label = f"`{r['segment']}`" + (f" via `{r['specialist']}`" if r['specialist'] else "")
            lines.append(f"- {label}: {r['text']}")
        if len(af["refactor_suggestions"]) > 50:
            lines.append(f"- *... {len(af['refactor_suggestions']) - 50} more "
                         f"in synthesis.json*")
        lines.append("")

    if af.get("concerns"):
        lines.append("## Concerns / smells (aggregated)")
        # group by segment for readability
        by_seg = defaultdict(list)
        for c in af["concerns"]:
            by_seg[c["segment"]].append(c["text"])
        for seg, items in sorted(by_seg.items()):
            lines.append(f"### {seg}")
            for it in items[:5]:
                lines.append(f"- {it}")
            lines.append("")

    if af.get("cross_segment_hints"):
        lines.append("## Cross-segment hints (raw, for routing)")
        for h in af["cross_segment_hints"][:30]:
            lines.append(f"### From {h['segment']}")
            lines.append(h["text"])
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
