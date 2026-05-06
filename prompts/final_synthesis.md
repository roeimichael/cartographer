# Final Synthesis — main-agent template

After Phase 5 (`scripts/synthesize.py`) writes `synthesis.json` and `synthesis.md`, you (the main agent) write `FINAL_REPORT.md` using the structure below.

Read inputs:
- `.cartographer/project-map.json` — the raw graph
- `.cartographer/segments.json` — segment list with metadata
- `.cartographer/synthesis.json` — cross-cutting findings (machine-generated)
- `.cartographer/synthesis.md` — same, human-readable
- `.cartographer/reports/*.md` — every per-segment report

Then write `.cartographer/FINAL_REPORT.md` with this exact structure:

---

```markdown
# Project Cartographer — Final Report

**Project**: <root path>
**Files**: <count>  ·  **LOC**: <count>  ·  **Segments**: <count>
**Languages**: <list>  ·  **Integrations**: <list>

## 1. Executive summary

5–10 bullets. Each bullet is a finding with action implied. Lead with the highest-impact items. Examples:
- "3 segments use `requests`, 2 use `httpx`. Standardize on httpx (already dominant by LOC). [→ §4.1]"
- "`format_date` reimplemented in 5 segments. Centralize in `src/utils/time.py`. [→ §4.2]"
- "auth segment uses snake_case, rest of project uses camelCase. Migration sketch in §5."

## 2. Project map

Embed the Mermaid diagram from `.cartographer/segments.mmd` inside a fenced code block:
\`\`\`mermaid
<contents of segments.mmd>
\`\`\`

If the project has more than ~30 segments, summarize visually instead — show only the top 15 by complexity and a "+N other segments" node.

## 3. Segment inventory

A table — one row per segment, sorted by complexity descending:

| Segment | Files | LOC | Integrations | Endpoints | Concerns |
|---------|-------|-----|--------------|-----------|----------|
| ...     | ...   | ... | ...          | ...       | ...      |

Pull "Concerns" from each report's "Concerns / smells" section — one short phrase per segment.

## 4. Cross-cutting findings

Surface the synthesis.json findings, grouped:

### 4.1 Duplicate / near-duplicate functions
From `synthesis.duplicates`. Show top 20. Include score, both locations, both segments. End with a one-line refactor recommendation per pair where the recommendation is non-obvious.

### 4.2 Centralization candidates
From `synthesis.centralization_candidates`. For each pattern (sql_helpers, validators, etc.):
- Which segments are affected
- Concrete suggested location for the centralized version (e.g. `src/utils/sql.py`)
- Migration cost estimate (S/M/L based on segment count and complexity)

### 4.3 Naming convention drift
From `synthesis.naming_outliers`. List outlier segments and what convention they use vs. project majority. Include a one-paragraph rename plan if the drift is significant.

### 4.4 Style fingerprint outliers
From `synthesis.style_outliers`. Segments with notably different LOC-per-symbol or other fingerprint metrics. Note: outliers are not always wrong — sometimes they reflect legitimate differences (e.g. data layer naturally has shorter functions). Flag, don't condemn.

## 5. Refactoring backlog

Aggregate the "Refactor suggestions" sections from every per-segment report PLUS the cross-cutting recommendations. Deduplicate. Rank by **impact ÷ effort**. Format:

| Priority | Where | What | Why | Effort |
|----------|-------|------|-----|--------|
| P0 | `src/utils/` | Extract shared `format_date` | 5 reimplementations | S |
| P1 | `src/auth/` | Migrate to camelCase | Aligns with rest of project | M |
| ... | ... | ... | ... | ... |

Cap at 25 items. The user will pick which to execute.

## 6. Inferred style guide

Based on majority conventions across all segments, write a short style guide for this project:

- **Naming**: <observed dominant convention>
- **Error handling**: <observed dominant style>
- **Async**: <observed pattern>
- **Logging**: <observed pattern>
- **Type hints**: <observed coverage>
- **Test pattern**: <if observed>

Keep it under one screen. This becomes the seed for a CONTRIBUTING.md or CLAUDE.md.

## 7. Per-segment links

Bullet list of links to every individual segment report, for the user to drill into:
- [supabase@src/db](.cartographer/reports/supabase_src_db.md)
- [telegram@src/bot](.cartographer/reports/telegram_src_bot.md)
- ...

## 8. Coverage notes

What got skipped:
- Files that failed to parse (count + list, from project-map.json's `parse_errors`)
- Segments marked "needs manual review" (from failed subagents)
- Languages not covered by current detectors

This section keeps the report honest about what wasn't checked.
```

---

## Tone for the final report

- Direct. No "it appears that" / "perhaps consider".
- File-pinned. Every claim points to a path.
- Ranked by impact, not alphabetical.
- The user is the lead engineer; assume technical fluency.

## Length budget

- Executive summary: ≤ 10 bullets
- Cross-cutting findings (§4): ≤ 2 screens
- Refactor backlog (§5): ≤ 25 items
- Total: aim for one document the user can read in 10 minutes and act on.
