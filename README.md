# project-cartographer

A **Claude Code skill** that audits large codebases — repos with hundreds of files, multiple integrations, and cross-cutting consistency concerns. Conversational from start to finish; ships with 17 specialist reviewer roles; can map, review, and apply fixes.

> **For users**: install the skill, then in Claude Code say something like *"audit this project"* or *"map out my codebase"*. The skill walks you through scope → questions → review → backlog → fixes, asking for confirmation at each gate.

> **For power users / CI**: every phase is a standalone Python script under `scripts/`. The convenience runner is `./run_pipeline.sh <project_root>`. Use `--readonly` to keep outputs out of the repo.

## What it does — the short version

1. **Builds a multi-layer graph**: file imports + function call graph (Python AST-precise) + class hierarchy. TS path aliases resolved.
2. **Traces pipelines** from entry points (API handlers, `main()`, workers) through the call graph — produces one Mermaid flowchart per pipeline.
3. **Per-endpoint deep call trace + OpenAPI extraction** — each API endpoint gets a card with request/response schema, internal call tree, top external dependencies, and cross-endpoint reuse map.
4. **Detects functional segments** (per domain — `auth`, `watchlists`, `backtests`, ...).
5. **Matches a specialist reviewer** to each segment from a 17-strong library.
6. **Asks you what to focus on** before dispatching agents.
7. **Dispatches review subagents** in waves of ≤5.
8. **Synthesizes** duplicates, naming drift, centralization candidates, style outliers.
9. **Produces a final report** with a refactor backlog ranked P0–P3.
10. **Applies fixes** (opt-in, behind a confirmation gate) — fix subagents make surgical edits, report diffs, skip cleanly when the bug isn't where claimed.

The split between **scripts** (deterministic, ~30s for 300 files) and **subagents** (judgment, costs scale with segment count) keeps the agentic phase small. A 1000-file repo with 20 segments costs ~20 subagent invocations, not 1000 file reads.

## What's new in v0.8

- **Phase 7 polish** — `finalize_fixes.py` creates a branch before fixes, aggregates diffs into `fix_summary.md`, runs your test command (`--test-cmd "pytest -x"`)
- **Progress heartbeat** — `cartographer status` shows the live phase/step/percentage; useful on long runs
- **skills.sh scaffolding** — `agents/_registry.yml` + `install_specialist.py` for opt-in dynamic specialist install (registry ships mostly empty; users contribute verified entries)
- **Real example outputs** — `examples/stocksCorrelation/` shows actual segment list, endpoint cards, pipeline diagrams from a real run

## What's new in v0.7

- Conversational gates at every decision point (segments → specialists → cost → review → fixes)
- Phase 0 clarifying questions captured before any work
- Synthesizer fix — agent reports' findings are now aggregated (silent gap in v0.6)
- 3 new specialists: mobile, cli-tool, test-suite
- Specialist coverage gaps surfaced when no installed specialist fits a segment
- `--readonly` mode — outputs go to `~/.cartographer/<hash>/`

See [CHANGELOG.md](CHANGELOG.md) for the full history.

## Installing

This is a Claude Code skill. **Drop the folder into your skills directory** (location depends on your Claude Code client — check Claude Code docs). On invocation, Claude Code reads `SKILL.md` and walks the user through.

If you want to run the scripts manually:

```bash
pip install -r requirements.txt --break-system-packages

# All scripted phases (1, 1.5, 1.6, 2, 3, 3.5) at once:
./run_pipeline.sh /path/to/your/repo

# Or with --readonly (keeps your repo clean):
./run_pipeline.sh /path/to/your/repo --readonly

# After Claude Code has dispatched Phase 4 (review subagents) and reports
# are in <output>/reports/, run synthesis:
python scripts/synthesize.py <output>/reports/ \
    --map <output>/project-map.json \
    --output <output>/synthesis.json
```

## Triggering the skill in Claude Code

These phrasings all work:

- "Map out my project"
- "Audit this codebase"
- "Find duplication / inconsistencies across the repo"
- "Build a UML / dependency diagram for this project"
- "I have hundreds of files spread across {Supabase, Telegram, AI APIs, ...} — analyze them"

The skill **always asks before doing anything heavy**. Phase 0 collects scope + clarifying answers; Phase 4 dispatch is gated by an explicit cost confirmation; Phase 7 fixes are gated by a separate opt-in.

## Specialist agent library (17 roles)

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
| `frontend-designer-reviewer` | Visual polish, motion, library recommendations |
| `mobile-reviewer` | iOS / Android / RN / Flutter — lifecycle, permissions, native bridge |
| `cli-tool-reviewer` | Flag naming, exit codes, stdout/stderr discipline, --json mode |
| `test-suite-reviewer` | Mock hygiene, flake risk, coverage shape |
| `file-storage-reviewer` | Upload safety, signed URLs, FS leaks |
| `realtime-streaming-reviewer` | Channels, broadcast scope, auth-per-message |
| `devops-config-reviewer` | Image hygiene, secrets, env drift, pins |
| `caching-reviewer` | TTL, invalidation, stampede, key collisions |
| `generalist-reviewer` | Fallback for everything else |

Each specialist is a markdown file under [`agents/`](agents/) with YAML frontmatter declaring triggers and priority. The matcher picks the highest-scoring match per segment. Override per-segment by editing `assigned_agent` in `wave_plan.json` before Phase 4.

To add a new specialist: drop a new `agents/<name>-reviewer.md` with frontmatter; the matcher auto-discovers it. See [`agents/AGENTS.md`](agents/AGENTS.md) for the catalog and [`docs/customization.md`](docs/customization.md) for the extension guide.

## Languages supported

- **Python** — precise, AST-based (full call graph + class hierarchy with bases/methods/fields)
- **JavaScript / TypeScript** — regex-based, best-effort (works for typical code; misses exotic syntax)
- **Go** — regex-based, best-effort

Tree-sitter for non-Python is on the roadmap. See [`docs/customization.md`](docs/customization.md) to add a language.

## Output structure

After a full run, the output dir contains:

```
project-map.json          full graph (files, edges, symbols, classes, calls, endpoints, integrations)
project-map.mmd           Mermaid: file-level dependency graph
class_diagram.mmd         Mermaid: classDiagram with bases, methods, fields
pipelines.json            entry → call tree per pipeline
pipelines.mmd             Mermaid: combined flowchart (top 10 pipelines)
pipelines/                one Mermaid flowchart per pipeline
openapi.json              real or synthetic OpenAPI spec
endpoints.json            per-endpoint trace summary
endpoints.md              endpoint index + cross-endpoint reuse hot-list
endpoints/                one detail card per endpoint
segments.json             segments with metadata
segments.mmd              Mermaid: segment overview
wave_plan.json            waves + specialist assignments
specialist_gaps.json      segments where no specialist matched well
scope.json                user's Phase 0 answers (goal, skip-paths, ...)
reports/                  per-segment specialist review reports
synthesis.json            cross-cutting findings + aggregated agent findings
synthesis.md              human-readable synthesis
FINAL_REPORT.md           consolidated deliverable
backlog.md                refactor backlog (Phase 7 input)
fix_reports/              per-fix diff reports (after Phase 7)
```

## Design notes

- **Why scripts + subagents?** Deterministic work (parsing, graph algos, fuzzy matching) is cheap as a script and unreliable as an LLM call. Judgment work (interpreting code, recommending refactors) is what subagents are for.
- **Why waves of 5?** Empirically, 30 agents at once thrashes context limits. Waves of 5 with strict schemas keep memory bounded and let later waves reference earlier results.
- **Why per-segment?** A subagent reviewing one well-defined segment produces a tight, structured report. A subagent told to "review the whole repo" produces vague prose.
- **Why explicit gates?** A 75-segment audit costs real money. The user should see segments + specialist assignments + cost estimate before any subagent fires. Single-shot opt-in is too coarse.
- **Why no embeddings?** Function-name fuzzy matching catches most cross-segment duplication. Embeddings shine for semantic body matching (different syntax, same intent) — that's a roadmap item, not core.

## License

MIT — see [LICENSE](LICENSE).

## Status

**v0.8** — release candidate. Roadmap:

- Skills.sh dynamic specialist install (currently: gaps surfaced, install is manual)
- Tree-sitter for JS/TS call resolution
- Semantic dedup via code-specialized embeddings (optional)
- Incremental re-run mode (re-analyze only changed segments)
- Phase 7 polish: branch creation, test running after fixes, unified diff summary
- More specialists: graphql-api, grpc, notebook, docs, cicd

## Contributing

Specialist roles, integration detectors, and language parsers are all designed for easy extension. See [`docs/customization.md`](docs/customization.md). PRs welcome.
