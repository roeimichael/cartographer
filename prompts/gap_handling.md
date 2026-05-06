# Gap-handling questions — post Phase 6

After `FINAL_REPORT.md` is produced, the main agent asks the user how to handle the findings before any code change happens. Two question rounds:

## Round 1 — Triage

Show the backlog, then ask:

> The audit produced **N findings** ranked P0–P3:
>
> - P0 (critical correctness / security): X items
> - P1 (high-impact refactor): Y items
> - P2 (consistency / polish): Z items
> - P3 (nice-to-have): W items
>
> What do you want to do?
>
> 1. **Apply all P0 now** (safest path — the rest stay in the backlog)
> 2. **Walk through them one at a time** so you can approve/reject each
> 3. **Apply only the items I list** — paste IDs (e.g. fix-1, fix-3, fix-7)
> 4. **Ship the report only** — no fixes, you'll handle manually
> 5. **Something else** — describe

## Round 2 — Decisions only the user can make

Some findings need human input. Surface these explicitly before asking about fixes:

> A few items need decisions only you can make. Want to walk through them now?
>
> - **Library choice** (frontend-designer recs): pick GSAP vs Motion for hero animation; pick visx vs recharts for the data viz.
> - **Style standard**: project mixes snake_case (43%) and camelCase (57%). Which do you want enforced?
> - **Schema reconciliation**: 3 different versions of `Position` shape exist. Which is the correct contract?
> - **Asset sourcing**: Lottie file for the loader, video for the hero — these need files you provide.
> - **Architectural calls**: deprecate the `scripts/legacy/` folder, or keep maintaining it?

For each decision item, present:
- The current state (with file refs)
- Two or three concrete options
- The implication of each
- A default if user says "your call"

## Round 3 — Pre-fix safety

Before dispatching Phase 7 fix agents:

> Phase 7 will modify your code. Confirmations:
>
> 1. Should I create a new git branch first? (default: `cartographer/fixes-<date>`) [Y/N]
> 2. Run tests after fixes? If yes, give me the command (e.g. `pytest`, `npm test`, `cargo test`).
> 3. Any items from the list you want to **exclude** from auto-fix? (E.g. ones that need redesign rather than mechanical edit.)

## Tone

- Be direct, not consultative. The user has just spent tokens on the audit; they want to act, not be polled forever.
- Default to a sensible option if user says "default" or just hits enter mentally.
- Never propose fixing a P0 without acknowledging that user owns the decision to apply it.

## Output

Translate user answers into:

```json
{
  "fix_selection": ["fix-1", "fix-3", "fix-7"],
  "decisions": {
    "style_standard": "snake_case",
    "schema_authority": "src/api/models/positions.py",
    "library_choice_animation": "framer-motion"
  },
  "branch_name": "cartographer/fixes-2026-05-07",
  "test_command": "pytest tests/ -x",
  "excluded_fixes": ["fix-9 (needs redesign discussion)"]
}
```

Save to `.cartographer/fix_selection.json`. Pass to the Phase 7 dispatcher.
