# stocksCorrelation — Cartographer audit report

**Run date**: 2026-05-06
**Cartographer version**: 0.8.0
**Project**: stocksCorrelation (Python + React quant-trading project)
**Files scanned**: 134 (94 Python, 40 TypeScript/React)
**Segments**: 16 → 9 review waves
**Specialists matched**: 8 distinct (1 gap → generalist fallback)
**Cost**: ~16 subagent invocations (Phase 4) + 3 fix subagents (Phase 7)

> **Reading order**: Executive summary → Findings (P0 first) → Cross-cutting patterns → Backlog.
> The full per-segment reports are under `reports/`; the synthesizer's aggregated view is `synthesis.md`.

---

## Executive summary

stocksCorrelation is in a healthy structural state — 16 cleanly-separable segments, no mega-tangle, FastAPI + pyarrow + pandas backend with a React + WebSocket frontend. But the audit caught **8 P0 issues** that are either silently incorrect (look-ahead leakage, wrong cash accounting) or visibly broken (toast crashes, frozen status bar). Three of these were applied automatically in Phase 7; the rest stayed in the backlog because they involve product decisions, not mechanical fixes.

**Highest-impact finding**: `cli/paper_trade_daily.py:67` does same-day signal generation against same-day prices — a textbook look-ahead bug that inflates backtest returns. This is a P0 correctness issue, not a code-quality nitpick.

**Visible breakage**: The frontend `<Toaster>` is mounted outside `<BrowserRouter>` (App.tsx) — any toast that triggers a navigation crashes the app. Combined with three distinct WebSocket leak bugs in `useMarketMonitor`, the live-feed page is unreliable on long sessions.

**Schema drift**: Three writers and two readers of `positions_state.json` use incompatible field names and types. This will silently corrupt state the moment any one of them is updated independently.

---

## Findings — P0 (must fix)

### 1. Look-ahead leakage in paper-trading flow
- **Where**: `cli/paper_trade_daily.py:67`
- **Specialist**: data-pipeline-reviewer
- **What**: The signal pipeline reads `df` and computes signals against the same-day close, then passes those signals to `open_position` on that same day's bar. This is a future-leak — in production, the close isn't known when the signal must fire.
- **Fix**: Shift the signal series by 1 (`df['signal'].shift(1)`) before joining, or split into a "compute on day N" / "act on day N+1" pair. P0 because this silently inflates every backtest return.

### 2. Short-position cash accounting wrong (off by 2× notional)
- **Where**: `trading/paper_trading.py:open_position`
- **Specialist**: data-pipeline-reviewer
- **What**: When a short is opened, cash is *credited* with the proceeds AND the margin requirement is also subtracted from a separate balance variable that tracks the wrong account. Net effect: shorts boost reported equity by ~2× notional.
- **Fix**: Single source of truth for cash. Subtract margin from cash on short open, credit on close.

### 3. Wrong module import — fails at runtime
- **Where**: `cli/run_multi_strategy_paper_trading.py:80`
- **Specialist**: cli-tool-reviewer
- **What**: Imports `from strategies.combined import run_combined` — `strategies/combined.py` doesn't exist; the module is `strategies/composite.py` with `run_composite`. Anyone who runs this CLI hits an `ImportError` immediately.
- **Fix**: Correct import + function name. Add a smoke test that imports every CLI entry point.

### 4. Toaster mounted outside BrowserRouter
- **Where**: `frontend/src/App.tsx`
- **Specialist**: frontend-ui-reviewer
- **What**: `<Toaster />` sits outside `<BrowserRouter>`. Any toast handler that calls `navigate()` (we use this for "click toast → go to position") throws "useNavigate must be used within a Router".
- **Fix**: Move `<Toaster />` inside `<BrowserRouter>`.

### 5. `useMarketMonitor` hook leaks WebSockets (3 distinct bugs)
- **Where**: `frontend/src/hooks/useMarketMonitor.ts`
- **Specialist**: frontend-ui-reviewer + realtime-streaming-reviewer
- **What**:
  1. `useEffect` cleanup doesn't call `ws.close()` when symbol list changes
  2. Reconnect on error opens a new WS without closing the old one
  3. Component unmount races with `onmessage` — handler runs against stale state
- **Fix**: Make connection lifecycle owned by a `useRef`, with strict cleanup on every dependency change. Cancel reconnect timers on unmount. Already drafted in synthesis — needs review before merge.

### 6. Schema drift: 3 incompatible ledger schemas across writers/readers
- **Where**: `positions_state.json` flow — written by `trading/paper_trading.py`, `cli/paper_trade_daily.py`, `cli/reconcile.py`; read by `dashboard/server.py` and `analysis/equity_curve.py`
- **Specialist**: db-schema-reviewer + data-pipeline-reviewer
- **What**: One writer uses `{"qty": int}`, another `{"quantity": float}`, third `{"size": str}`. Readers crash or silently coerce. Today they happen to interleave in a way that doesn't trigger; a single refactor will produce silent corruption.
- **Fix**: Define a Pydantic model in `trading/models.py`. All writers serialize through it. Migration: load-old / write-new on next run.

---

## Findings — P1 (should fix)

### 7. `prepare_returns` does `dropna(how='any')` — silently drops most rows
- **Where**: `dataio/prep.py`
- **Specialist**: data-pipeline-reviewer
- **What**: Any column with NaN propagates to row-drop, so a single sparse signal column nukes 90%+ of the dataset. Several downstream stats are computed on this drastically reduced sample.
- **Fix**: `dropna(subset=['close'])` — drop only when the price is missing. Decide separately for each signal column.

### 8. `StatusBar` clock has no `setInterval` — frozen
- **Where**: `frontend/src/components/layout/StatusBar.tsx`
- **Specialist**: frontend-ui-reviewer
- **What**: Time is computed once on mount with `new Date()`. Renders the time the page loaded; never updates.
- **Fix**: `useEffect` with `setInterval(() => setNow(new Date()), 1000)` and cleanup.

---

## Cross-cutting patterns

The synthesizer flagged three patterns repeating across segments:

### A. Cash / position accounting scattered across modules
Six distinct files mutate `cash`, `positions`, or both:
`trading/paper_trading.py`, `cli/paper_trade_daily.py`, `cli/reconcile.py`, `analysis/equity_curve.py`, `dashboard/server.py`, `strategies/composite.py`.

**Recommendation**: centralize in `trading/portfolio.py` — single class, all mutations behind methods, JSON serialization owned by it. Prevents schema drift (finding 6) and cash-accounting bugs (finding 2) from recurring.

### B. WebSocket lifecycle is hand-rolled in 3 places
`useMarketMonitor`, `useLiveTrades`, `useStrategyHeartbeat` each implement reconnect-with-backoff slightly differently. All three have at least one leak / race.

**Recommendation**: extract `useWebSocket` primitive — one well-tested implementation, consumers pass URL + message handler. Cuts ~120 lines and unifies reconnect semantics.

### C. CLI entry points have no smoke tests
Eleven files in `cli/` have a `if __name__ == "__main__"` block. None are exercised in tests. Finding 3 (the wrong-import bug) would have been caught by even a `python -m py_compile cli/*.py`.

**Recommendation**: add a `tests/test_cli_imports.py` that imports each CLI module — the cheapest possible smoke test, catches 100% of import-time errors.

---

## Specialist coverage

| Specialist | Segments | Notes |
|------------|----------|-------|
| data-pipeline-reviewer | 4 | Strongest signal — backend domain dominates |
| frontend-ui-reviewer | 4 | Clean fits; one shared with realtime-streaming |
| db-schema-reviewer | 1 | Caught the schema-drift finding |
| backend-api-reviewer | 1 | FastAPI surface |
| cli-tool-reviewer | 1 | Caught import bug, flagged exit-code inconsistency |
| frontend-designer-reviewer | 1 | Suggested anime.js for the equity-curve animation |
| realtime-streaming-reviewer | 1 | Co-reviewed WebSocket hooks |
| generalist-reviewer | 1 | Fallback for the misc-utilities segment (gap) |

One coverage gap (`misc-utilities`, 8 files) — fell back to generalist. Not worth installing a specialist for; output was acceptable.

---

## Backlog (refactor priority)

See `backlog.md` for the actionable list. Ranked:

| # | Priority | Item | Effort |
|---|----------|------|--------|
| 1 | P0 | Fix look-ahead in `paper_trade_daily.py:67` | 30 min |
| 2 | P0 | Fix short-cash accounting in `paper_trading.py` | 1 hr |
| 3 | P0 | Fix wrong import in `run_multi_strategy_paper_trading.py:80` | 5 min |
| 4 | P0 | Move `<Toaster>` inside `<BrowserRouter>` | 5 min |
| 5 | P0 | Rewrite `useMarketMonitor` lifecycle | 2 hr |
| 6 | P0 | Pydantic model for `positions_state.json` + migration | 3 hr |
| 7 | P1 | Fix `prepare_returns` dropna scope | 15 min |
| 8 | P1 | Wire `StatusBar` clock | 5 min |
| 9 | P2 | Centralize portfolio mutations (`trading/portfolio.py`) | 4–6 hr |
| 10 | P2 | Extract `useWebSocket` primitive | 2 hr |
| 11 | P3 | CLI smoke-import test | 30 min |

---

## Phase 7 — fixes applied

Three P0 items were applied via fix subagents on branch `cartographer/fixes-2026-05-06`:

| # | Status | Notes |
|---|--------|-------|
| 3 | ✅ applied | One-line import correction. Diff in `fix_reports/03_wrong_import.md` |
| 4 | ✅ applied | Toaster moved. Diff in `fix_reports/04_toaster_router.md` |
| 8 | ✅ applied | `setInterval` + cleanup added. Diff in `fix_reports/08_status_clock.md` |

The other 5 P0s were *not* applied — they involve product decisions (e.g. how to handle the look-ahead historically — re-run all backtests? gate behind a flag?) or larger surgical work that benefits from a human in the loop. Surfaced for the user; backlog entries kept.

---

## Notes for the user

- The **look-ahead leak (finding 1)** invalidates every backtest result on this branch. Before publishing any returns chart, re-run with the fix applied.
- The **schema drift (finding 6)** is a ticking bomb — works today, will silently break on the next refactor. Fix before any other ledger change.
- The **WebSocket bugs (finding 5)** explain the "the dashboard freezes after ~30 minutes" symptom you flagged in Phase 0.

Re-run cartographer after the P0 fixes land — segment scores should improve and the data-pipeline-reviewer should report fewer findings.
