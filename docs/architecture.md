# Architecture

## The split: scripts vs. subagents

The skill divides work into two kinds:

| Phase | Type | Why |
|-------|------|-----|
| 1. Map | Python script | Deterministic. Parsing 500 files in a script costs ~30s and zero LLM tokens. |
| 2. Segment | Python script | Graph algorithms (connected components, integration scoring) are not LLM-shaped problems. |
| 3. Plan waves | Python script | Topological sort. Trivial without LLM. |
| 4. Review | **Subagents** | Reading code and forming opinions is exactly what the model is for. |
| 5. Synthesize | Python script + main agent | Fuzzy matching + counting → script. Final write-up → main agent. |
| 6. Final report | Main agent | Composition is judgment work. |

This pattern matters because the agentic part (Phase 4) scales with the **number of segments**, not the number of files. A 1000-file repo with 20 segments costs ~20 subagent invocations, not 1000 file reads in the main loop.

## Why connected components for segmentation

Code naturally clusters by import dependencies. A Telegram handler imports the bot framework + the Supabase client + a logger; a payment endpoint imports Stripe + the same Supabase client + the same logger. Connected components catches the strong edges (the shared Telegram code) while integration scoring distinguishes the components by purpose.

This works less well for monorepos with deep cross-imports — there everything ends up in one component. The split-oversized step in `classify_segments.py` falls back to directory-based partitioning when a component is too big.

## Why waves of 5

Three constraints push toward small waves:

1. **Context-window pressure on the orchestrator.** Each subagent's report comes back into the main agent's context. 30 reports of 200 lines each = 6000 lines of context just for the handoff.
2. **Coordination cost.** If wave N+1 should reference wave N's findings (e.g. "auth segment uses snake_case, so other segments should align"), you need waves to actually be sequential — not just batched.
3. **Failure mode containment.** If one subagent fails, you re-dispatch one — not the whole batch.

Five is empirical. Three works too. Ten is too many.

## Why strict schemas for subagent reports

Phase 5 (synthesis) is a Python script that parses every report. If reports are free-form prose, the script can't extract symbol inventories or naming patterns. The schema in `prompts/segment_review.md` is the contract: subagents fill in the blanks, the script reads the blanks. Loose schemas defeat the whole point of having a synthesis step.

## Why no vector embeddings (yet)

For code, **exact and fuzzy name matching** catches the bulk of the cross-segment duplication you actually want to fix. The synthesis script uses `rapidfuzz` (or `difflib` as a fallback) to match function names across segments at ~82% similarity. That catches `formatDate` / `format_date` / `formatTimestamp` / `to_date_string` — which is most of what users mean by "duplicate code".

Embeddings shine for two cases this skill currently doesn't try to solve:
1. **Semantic body matching** — two functions that look different but do the same thing.
2. **Concept queries** — "show me everything related to authentication".

Both are good additions if you need them. The synthesis script is structured so a new finding type ("semantic_dupes") can be added without touching the rest of the pipeline. See `docs/customization.md` §4.

## Why opt-in at Phase 0

Token cost. A 30-segment audit at ~3-5 minutes per subagent is real time and real money. The skill makes the user say "proceed" before any subagent is dispatched, and the scripts (Phases 1-3) run cheaply enough that the user gets the segment list and wave plan to review before committing.

## Failure semantics

The `.cartographer/` directory holds all state. If a run is interrupted:
- Re-running Phase 1 is idempotent (just overwrites).
- Phase 2 is idempotent.
- Phase 3 is idempotent.
- Phase 4 should check for existing reports and skip segments that already have them. The main agent is responsible for this; the SKILL.md instructs it to.
- Phase 5 is idempotent (overwrites synthesis).

This means a user can abort, look at intermediate output, and resume — without paying for the same work twice.
