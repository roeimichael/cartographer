# Example outputs — stocksCorrelation

These are real outputs from running project-cartographer on a 134-file Python + React quant-trading project (FastAPI backend, pyarrow/pandas data layer, React frontend with WebSocket live feed).

## What's here

```
segments.json              # 16 detected segments, full metadata
segments.mmd               # Mermaid: segment overview
wave_plan.json             # 9 review waves + specialist assignments
specialist_gaps.json       # 1 segment flagged as no-good-match (frontend config bundle)
class_diagram.mmd          # 36 classes with bases, methods, fields
pipelines.mmd              # combined Mermaid (top 10 pipelines)
pipelines.json             # 11 traced pipelines (trimmed — full nodes elided)
pipelines/                 # 3 sample per-pipeline Mermaid flowcharts
openapi_summary.md         # 4-endpoint API table
endpoints.md               # endpoint trace index + cross-endpoint reuse hot-list
endpoints/                 # 3 sample per-endpoint detail cards
```

`project-map.json` (~800KB), `class_diagram.mmd` full body, and full `pipelines/` are included for the top items only — to keep this folder browsable.

## What you'd see in your own run (additionally)

When Phase 4 review subagents run, they produce per-segment reports under `reports/<segment>.md`. Phase 5 synthesizes them into `synthesis.md` and Phase 6 produces a `FINAL_REPORT.md` with a refactor backlog. Phase 7 (opt-in) applies fixes and writes per-fix reports under `fix_reports/`.

For an end-to-end walkthrough including the agent-review phase, see the parent project's [README.md](../../README.md) and [SKILL.md](../../SKILL.md).

## Notable findings from the actual stocksCorrelation run

The audit caught real bugs in the project:

| Finding | Severity | Where |
|---------|----------|-------|
| Look-ahead leakage in paper-trading flow | P0 | `cli/paper_trade_daily.py:67` |
| Short-position cash accounting wrong (off by 2x notional) | P0 | `trading/paper_trading.py:open_position` |
| Wrong module import — fails at runtime | P0 | `cli/run_multi_strategy_paper_trading.py:80` |
| Toasters mounted outside `<BrowserRouter>` (crash on toast+navigate) | P0 | `frontend/src/App.tsx` |
| `useMarketMonitor` hook leaks WebSockets (3 distinct bugs) | P0 | `frontend/src/hooks/useMarketMonitor.ts` |
| Schema drift: 3 incompatible ledger schemas across writers/readers | P0 | `positions_state.json` flow |
| `prepare_returns` does `dropna(how='any')` — silently drops most rows | P1 | `dataio/prep.py` |
| `StatusBar` clock has no `setInterval` — frozen | P1 | `frontend/src/components/layout/StatusBar.tsx` |

3 of these were applied via Phase 7 — see [the Phase 7 validation log](../../CHANGELOG.md#v06--2026-05-06) for the actual diffs. The rest stayed in the backlog for the user to handle (some involve product decisions, not mechanical fixes).
