---
name: project-cartographer
version: 0.8.0
description: Map, audit, and review large multi-segment codebases (hundreds of files, multiple integrations like Supabase, Telegram, Vercel, AI APIs, file systems, queues, etc.) by building a dependency graph, detecting functional segments, then dispatching review subagents in controlled waves. Use this skill whenever the user wants to "map out", "audit", "review", "find duplication in", "enforce style across", "understand the structure of", or "analyze a large codebase" — especially when they mention many endpoints, multiple third-party integrations, or cross-cutting consistency concerns. Use even when the user does not say "skill" or "cartographer" — phrases like "review my whole project", "find inconsistencies across the repo", "build a UML of my project", or "I have hundreds of files spread across X, Y, Z services" should trigger this. This skill consumes substantial tokens and runs many subagents; it requires explicit upfront opt-in from the user before proceeding past Phase 0.
---

# Project Cartographer · v0.8.0

A multi-phase skill for mapping, segmenting, and auditing large codebases. Builds a dependency graph, detects functional segments (per integration / per pipeline), dispatches review subagents in waves of 5, and synthesizes cross-cutting findings (duplication, naming drift, refactor candidates, centralization opportunities).

## When to use this skill

Trigger this skill when the user wants holistic understanding or auditing of a project that:
- Spans hundreds of files
- Has multiple distinct integrations (e.g. Supabase, Vercel, Railway, Telegram, OpenAI/Anthropic, Google APIs, queues, file systems)
- Has multiple API endpoints across different functional domains
- Is suspected of having duplication, naming drift, or style inconsistency
- The user wants to refactor, modularize, or document end-to-end

Do NOT use this skill for small projects (<30 files) — agentic search handles those just fine. The overhead only pays off when the project is too large to hold in working memory.

## High-level flow

```
Phase 0    Scope & explicit opt-in
Phase 1    Build dependency graph + call graph + class model (scripted)
Phase 1.5  Trace pipelines from entry points through call graph (scripted)
Phase 1.6  Extract OpenAPI + per-endpoint deep call trace (scripted)
Phase 2    Detect & label segments (scripted)
Phase 3    Plan review waves (scripted)
Phase 3.5  Match a specialist agent to each segment (scripted)
Phase 4    Dispatch review subagents (Claude does this, in waves of ≤5)
Phase 5    Synthesize cross-cutting findings (script + main agent)
Phase 6    Produce final artifacts (FINAL_REPORT.md + backlog.md)
Phase 7    Apply backlog — dispatch fix subagents per backlog item (opt-in)
```

Phases 1–3.5 and 5 are deterministic Python scripts under `scripts/`. Phase 4 is the only "agentic" phase and is gated by the user's opt-in from Phase 0.

## Specialist agent library

The skill ships with **14 specialist reviewer roles** under `agents/`:

| Specialist | Reviews |
|------------|---------|
| `auth-security-reviewer` | Auth flows, tokens, sessions, secrets |
| `supabase-reviewer` | Supabase client, RLS, edge functions, realtime, storage |
| `db-schema-reviewer` | Schema, migrations, indexes, raw SQL |
| `telegram-bot-reviewer` | Handlers, FSM, webhook security, rate limits |
| `ai-pipeline-reviewer` | Models, prompts, caching, token budgets, structured output |
| `backend-api-reviewer` | Endpoints, validation, response shapes |
| `data-pipeline-reviewer` | ETL/ML correctness, leakage, NaN/index, perf, reproducibility |
| `queue-worker-reviewer` | Idempotency, retries, DLQ, backpressure |
| `webhook-integration-reviewer` | Sig verification, replay, outbound timeouts |
| `frontend-ui-reviewer` | Hooks, props, state, render perf, a11y |
| `file-storage-reviewer` | Upload safety, signed URLs, FS leaks |
| `realtime-streaming-reviewer` | Channels, broadcast scope, auth-per-message |
| `devops-config-reviewer` | Image hygiene, secrets, env drift, pins |
| `caching-reviewer` | TTL, invalidation, stampede, key collisions |
| `generalist-reviewer` | Fallback for everything else |

Each segment is auto-matched to the best specialist by Phase 3.5. See [`agents/AGENTS.md`](agents/AGENTS.md) for the catalog and matching rules.

---

## Phase 0 — Scope, clarifying questions, opt-in (REQUIRED, do not skip)

Three things happen here, in order:

### 0.1 — Scope estimate

Run a quick size scan and present it:

```bash
cd <project_root>
echo "Files:    $(git ls-files 2>/dev/null | wc -l || find . -type f -not -path '*/node_modules/*' -not -path '*/.git/*' | wc -l)"
echo "LOC:      $(git ls-files 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 || echo 'n/a')"
echo "Languages:" && git ls-files 2>/dev/null | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10
```

### 0.2 — Clarifying questions

Read `prompts/clarifying_questions.md` and ask the user 3–5 focused questions in **one message** (don't ping-pong). The goal is to capture: goal, skip-paths, known-issues, ground-truth docs, sensitive paths, test posture, budget.

Save answers to `.cartographer/scope.json`. The mapper, segmenter, and specialist matcher all consume this file downstream.

### 0.3 — Opt-in

After scope + answers, present a clear plan:

> Project: **X files / Y LOC** in {languages}.
> Goal (from your answer): {goal}.
> Excluded: {skip_paths}.
>
> Plan:
> 1. Build dependency graph + call graph + class model (~30s, scripted)
> 2. Trace pipelines + extract OpenAPI (~10s, scripted)
> 3. Detect ~N functional segments (scripted)
> 4. Match each to a specialist reviewer (scripted)
> 5. **GATE A** — confirm segmentation + assignments before dispatching agents
> 6. Dispatch ~M reviewer subagents in waves of 5 (~$X estimate)
> 7. Synthesize findings + final report
> 8. **GATE D** — review backlog, pick what to fix
> 9. Phase 7 (optional) — apply fixes via fix subagents
>
> Reply **"proceed"** to start, or describe a partial scope.

Do not proceed past 0.3 without explicit go-ahead.

---

## Phase 1 — Build dependency graph

Run the mapping script. It walks the repo, parses Python (AST-precise) / JS/TS/Go (regex), extracts:

- File imports → file-level edge graph (TS path aliases from `tsconfig.json` are resolved)
- Function/class/method definitions with one-line headers
- **Function call edges** (Python AST is precise; JS/TS regex is best-effort)
- **Class hierarchy** (bases, methods, fields)
- API endpoint declarations + handler symbol id
- External integration markers (Supabase, Telegram, OpenAI, scientific Python, ...)

```bash
python scripts/map_project.py <project_root> --output .cartographer/
```

Outputs:
- `.cartographer/project-map.json` — full graph: files, edges, symbols, classes, calls, endpoints, integrations
- `.cartographer/project-map.mmd` — Mermaid: file-level dependency graph
- `.cartographer/class_diagram.mmd` — Mermaid `classDiagram` of project classes (with methods + fields + inheritance)

If a language isn't yet supported, see `docs/customization.md`.

---

## Phase 1.5 — Trace pipelines from entry points

Run the pipeline tracer. It finds entry points (API endpoint handlers, `main()` functions, worker tasks) and BFS-walks the resolved call graph from each one. Each pipeline becomes a function-level "what calls what" diagram — the closest thing to a runtime UML you can build statically.

```bash
python scripts/trace_pipelines.py .cartographer/project-map.json --output-dir .cartographer/
```

Outputs:
- `.cartographer/pipelines.json` — list of pipelines (each with nodes, edges, top external calls)
- `.cartographer/pipelines.mmd` — combined Mermaid flowchart (top 10 pipelines by node count)
- `.cartographer/pipelines/<entry>.mmd` — one Mermaid flowchart per pipeline (clickable in IDEs)

Knobs: `--max-depth` (default 6), `--max-nodes` (default 60). Increase for deeper traces; decrease if pipelines balloon for utility-heavy code.

This phase is **the answer to "show me what calls what across the project."** The Mermaid output renders directly in GitHub, VS Code, Obsidian, and most markdown viewers.

---

## Phase 1.6 — Extract OpenAPI + per-endpoint deep call trace

For HTTP services, the API is the contract. This phase:

1. **Extract** the OpenAPI spec (3 strategies, tried in order):
   - **File**: any `openapi.json` / `openapi.yaml` / `openapi_tmp.json` at standard locations
   - **Live**: fetch from a running server if user passes `--live-url http://localhost:PORT/openapi.json` (or sets `CARTOGRAPHER_LIVE_URL`)
   - **Synthetic**: build a minimal OpenAPI 3.1 doc from endpoints already detected statically. Always works, schemas are minimal.

2. **Trace** each endpoint through the resolved call graph (deeper than Phase 1.5 — default depth 10, 120 nodes per endpoint).

```bash
python scripts/extract_openapi.py .cartographer/project-map.json \
    --output-dir .cartographer/ \
    [--live-url http://localhost:8000/openapi.json]

python scripts/trace_endpoints.py .cartographer/project-map.json \
    --output-dir .cartographer/
```

Outputs:
- `.cartographer/openapi.json` — the spec (real or synthetic), with our `x-cartographer.handler_id` annotation per operation
- `.cartographer/openapi_summary.md` — human-readable endpoint table
- `.cartographer/endpoints.json` — per-endpoint trace summary (machine)
- `.cartographer/endpoints.md` — index + reuse hot-list (functions called from 2+ endpoints)
- `.cartographer/endpoints/<METHOD>_<path>.md` — one detail card per endpoint with:
  - Request schema (params + body)
  - Response schema(s)
  - Internal call tree (Mermaid flowchart)
  - Internal modules touched (file → call count)
  - Top external calls (boundary view)
  - Cross-endpoint reuse map (which other endpoints share which symbols)

Use these cards as the **debug-mode view of the API**: each card shows what an endpoint actually calls when invoked, statically over-approximated. Combined with the OpenAPI surface, this gives the most complete API picture without needing to run the project.

If the user wants real runtime traces (cProfile / sys.settrace), they should run their server and pass `--live-url` to fetch the real OpenAPI; this skill does not invoke user code.

---

## Phase 2 — Detect & label segments

Run the segmentation script. It computes connected components on the import graph, then labels each component by dominant integration markers (Telegram, Supabase, OpenAI, file system, etc.).

```bash
python scripts/classify_segments.py .cartographer/project-map.json --output .cartographer/segments.json
```

Outputs:
- `.cartographer/segments.json` — array of segments with `name`, `root_files`, `member_files`, `integrations`, `complexity_score`, `endpoints`
- `.cartographer/segments.mmd` — Mermaid diagram with one subgraph per segment

After this step, **show the user the segment list** before dispatching agents. They may want to merge, split, or rename segments. Honor any adjustments.

---

## Phase 3 — Plan review waves

Run the wave planner. It groups segments into parallel waves (max 5 per wave) ordered by dependency depth so foundation segments are reviewed before consumers.

```bash
python scripts/plan_waves.py .cartographer/segments.json --output .cartographer/wave_plan.json
```

Output: `.cartographer/wave_plan.json` — ordered list of waves, each wave is a list of ≤5 segments to review in parallel.

---

## GATE A — Segment confirmation (BEFORE Phase 3.5)

After segments + waves are computed but **before** specialist matching, show the user the segment list and let them adjust:

> I detected **N segments**. Top 10 by complexity:
> [paste the top 10 from segments.json with file count + integrations]
>
> Anything to merge, split, or skip before I run the review agents?
>
> - "looks good" / "proceed" → continue
> - "merge X and Y" → merge those segments
> - "skip Z" → drop that segment from the wave plan
> - "split X by Y" → re-segment that subtree

Honor adjustments. Common ones the user might ask for: merge config-only segments into the parent domain; skip vendored / generated / legacy paths; rename a segment for clarity.

---

## Phase 3.5 — Match specialist agents to segments

Run the specialist matcher. It scores every segment against the catalog in `agents/` and assigns the best-fit specialist (e.g. a Telegram-heavy segment gets `telegram-bot-reviewer`, an SQL-heavy segment gets `db-schema-reviewer`).

```bash
python scripts/match_specialists.py .cartographer/wave_plan.json \
    --segments .cartographer/segments.json \
    --agents-dir agents/
```

This enriches `wave_plan.json` with `specialist_assignments`: `{segment_name: {assigned_agent, score, runners_up}}`. Show the user the assignments before Phase 4 — they may want to override (e.g. swap to `auth-security-reviewer` on a segment that touches auth even if it doesn't trigger the integration).

To override: edit the `assigned_agent` field for that segment in `wave_plan.json` directly.

---

## GATE B — Specialist confirmation + cost estimate (BEFORE Phase 4)

Show assignments + cost estimate. **This is the gate before the expensive part.**

> Specialist assignments:
> [paste from wave_plan.json — specialist count + per-segment listing of top 10 by complexity]
>
> If any segment scored < 1500 (no good specialist match), see `specialist_gaps.json` — those will use `generalist-reviewer` unless you specify otherwise.
>
> Cost estimate: ~M subagent runs × ~40K tokens avg = ~T tokens (~$E).
>
> Reply:
> - **"proceed"** → run all M
> - **"top N"** → only the N highest-complexity segments
> - **"skip generalist"** → only run segments with a specialist match
> - **"swap X to Y"** → reassign segment X to specialist Y
> - **"stop"** → ship the static analysis only (no Phase 4)

Do not dispatch Phase 4 without explicit confirmation here. This is **the** cost gate.

---

## Phase 4 — Dispatch review subagents (the actual review)

This is the only phase where Claude (the main agent) does the orchestration. For each wave in `wave_plan.json`:

1. Read `prompts/specialist_base.md` — universal subagent contract (input vars, output schema, universal rules).
2. For each segment in the wave, look up its `assigned_agent` in `wave_plan.json.specialist_assignments`, then **spawn a subagent in parallel** (use the Task tool). Compose the subagent's system prompt as:

   ```
   <contents of prompts/specialist_base.md>

   --- SPECIALIST ROLE ---

   <contents of agents/<assigned_agent>.md>
   ```

3. Pass the segment's metadata as the user prompt: `segment_name`, `integrations`, `file_list`, `output_path` (`.cartographer/reports/<segment_name>.md`), `project_root`, `specialist_role`.
4. **Wait for all subagents in the wave to finish** before starting the next wave. Do not start wave N+1 while wave N is running.
5. After each wave, briefly summarize progress (e.g. "Wave 2/5 complete — 10 segments reviewed by [auth-security-reviewer × 2, db-schema-reviewer × 3]").

**Important:** subagent reports follow a strict schema (see `prompts/specialist_base.md`). Phase 5 parses these reports. If the user asks to customize the report format, update `prompts/specialist_base.md` AND `scripts/synthesize.py` together. The per-specialist sections (e.g. "Endpoint inventory", "RLS audit") are **additive** — they appear under "Specialist findings" and don't break the parser.

### Wave dispatch pattern

Wave with segments + assignments:

```
auth_module       → auth-security-reviewer
telegram_bot      → telegram-bot-reviewer
supabase_layer    → supabase-reviewer
ai_chat           → ai-pipeline-reviewer
file_storage      → file-storage-reviewer
```

Spawn 5 subagents in parallel, each given:
- System prompt: `prompts/specialist_base.md` + matched `agents/<role>.md`.
- User prompt: segment metadata + output path.
- Output path: `.cartographer/reports/<segment_name>.md`.

Wait for all 5 to complete. Then proceed to next wave.


---

## Phase 5 — Synthesize cross-cutting findings

After all waves are complete, run the synthesis script. It reads every per-segment report, extracts symbol inventories, and runs cross-cutting analyses.

```bash
python scripts/synthesize.py .cartographer/reports/ --map .cartographer/project-map.json --output .cartographer/synthesis.json
```

What it detects:
- **Duplicate functions** — fuzzy matching on function names + signatures across segments
- **Near-duplicate logic** — similar function bodies in different segments (lightweight token-set similarity)
- **Naming convention drift** — segments that disagree on snake_case vs camelCase, abbreviations, etc.
- **Centralization candidates** — patterns appearing in 3+ segments (SQL helpers, enums, validators, error wrappers)
- **Style fingerprint divergence** — outlier segments by avg function length, comment density, paradigm

Outputs:
- `.cartographer/synthesis.json` — structured findings (now includes `agent_findings.refactor_suggestions`, `agent_findings.concerns`, `agent_findings.cross_segment_hints` aggregated from per-segment reports)
- `.cartographer/synthesis.md` — human-readable summary

---

## Phase 6 — Produce final artifacts

Read `synthesis.json` and write the final consolidated report. Use `prompts/final_synthesis.md` as the structure template.

The final report goes to `.cartographer/FINAL_REPORT.md` and includes:
1. Executive summary (5–10 bullets)
2. Project map (Mermaid diagram, embedded)
3. Segment inventory (table)
4. Cross-cutting findings (ranked by impact × effort)
5. Refactoring backlog (concrete, file-pinned suggestions)
6. Style guide draft (inferred from majority conventions)

Present `FINAL_REPORT.md` to the user. Offer to drill into any specific finding.

---

## GATE D — Triage + decisions (BEFORE Phase 7)

Read `prompts/gap_handling.md` and run the three rounds of questions:

1. **Triage** — which P0/P1/P2/P3 items to act on
2. **Decisions** — items needing human judgement (library choice, style standard, schema authority, asset sourcing, architectural calls)
3. **Pre-fix safety** — branch creation, test command, items to exclude

Save selections to `.cartographer/fix_selection.json`. Don't dispatch Phase 7 without this confirmation.

---

## Failure modes & recovery

- **Script can't parse a file**: log to `.cartographer/parse_errors.log`, continue. Don't fail the whole run on one bad file.
- **A subagent fails**: retry once with a more constrained prompt (file list only, no integration analysis). If it fails again, mark the segment as "needs manual review" in the final report.
- **Wave times out**: reduce wave size to 3 and retry the failed wave.
- **User aborts mid-run**: the `.cartographer/` directory holds all partial state. On resume, skip phases whose outputs already exist.

## Customization

The integration detectors (Phase 1) and segment heuristics (Phase 2) are designed to be extended. See `docs/customization.md` for how to add detectors for new frameworks/services. Drop a new detector module into `scripts/detectors/` — no changes needed to the core scripts.

## What this skill is NOT

- Not a linter — it identifies cross-cutting issues, not line-level defects.
- Not a security audit — no taint analysis, no CVE checks.
- Not a replacement for human review on critical refactors — it generates a backlog, the human prioritizes and executes.

---

## Phase 7 — Apply backlog (opt-in)

After Phase 6 produces `FINAL_REPORT.md` and a `backlog.md` (curated list of file-pinned fixes), the user can opt into Phase 7 to actually apply fixes via subagents.

### Backlog format (`backlog.md`)

Fenced blocks, one per fix:

```
\`\`\`fix-1
summary: Move Toasters inside <BrowserRouter>
severity: P0
files: frontend/src/App.tsx
location: frontend/src/App.tsx
description: |
  Toasters mounted outside <BrowserRouter>; useNavigate inside a toast
  handler will crash the app.
fix: |
  Move <Toaster /> and <Sonner /> inside <BrowserRouter> as siblings
  of <Routes>. Keep their order.
verification: tsc --noEmit
\`\`\`
```

### Build the dispatch plan

```bash
python scripts/apply_backlog.py .cartographer/backlog.md \
    --output .cartographer/fix_plan.json
```

This groups items into waves so no two items in a wave touch the same file (parallel-safe).

### Dispatch fix subagents

For each wave, spawn one subagent per fix item using `prompts/fix_agent.md` as the system prompt. Each fix agent:

- Reads only the files in `item.files`
- Verifies the bug exists at the claimed location
- Applies the smallest possible fix (`Edit` with exact strings, no rewrites)
- **Skips and reports** if the bug isn't where claimed (skipping is success)
- Writes a structured fix report to `.cartographer/fix_reports/<item.id>.md` with diff + verification result

After each wave, the main agent reviews the fix reports, runs `git diff` to confirm changes, and decides whether to proceed to the next wave or stop.

### Important constraints

- **Phase 7 modifies user code.** Only run after explicit opt-in, ideally on a clean branch.
- **Atomic per item.** Each fix is independent — partial application is acceptable.
- **Skipping is fine.** A "skipped" fix means the bug wasn't where claimed; that's useful signal, not a failure.
- **No drive-by cleanups.** The fix agent prompt forbids unrelated changes.
- **No new deps without permission.** If a fix needs a library, agent surfaces it as a Concern instead of installing.
