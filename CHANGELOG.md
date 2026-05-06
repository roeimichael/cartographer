# Changelog

## v0.8 — 2026-05-07

Production polish on Phase 7 + observability + scaffolding for skills.sh.

**Phase 7 polish — `scripts/finalize_fixes.py`**:
- `pre` mode: creates `cartographer/fixes-<date>` git branch before fixes (idempotent — re-uses existing). Refuses with uncommitted changes unless `--force`. Skips silently when not in a git repo.
- `post` mode: aggregates per-fix reports from `fix_reports/` into a unified `fix_summary.md` with applied/skipped/failed buckets, combined git diff, and optional test-run results. Writes `fix_summary.json` for programmatic consumption.
- Test runner: pass `--test-cmd "pytest -x"` (or `npm test`, etc.) — the script runs it after fixes, captures stdout/stderr tails, reports pass/fail.

**Progress observability**:
- New `scripts/_progress.py` — tiny zero-dep heartbeat helper. Each phase script writes `_progress.json` mid-run.
- New `scripts/cartographer_status.py` — read-side. Run during a long phase to see current step, % progress, elapsed time.
- `map_project.py` wired (more scripts to follow as they grow).

**skills.sh dynamic install scaffolding**:
- New `agents/_registry.yml` — maps integration labels → skills.sh package names. Ships mostly empty (with commented examples) because skills.sh doesn't expose a stable registry API; users + contributors add verified entries.
- New `scripts/install_specialist.py` — reads the registry, prints install plan, runs `npx skills add <pkg>` only with `--execute --allow-skill-install` (double flag = deliberate). Logs every install to `.cartographer/specialist_install.log`.
- `prompts/specialist_gap.md` updated with both "registry-empty" and "install-available" branches and explicit honesty about why we don't auto-discover.

**Real example outputs**:
- `examples/stocksCorrelation/` replaces the old fake sample with curated outputs from a real project run: 16 segments, 11 traced pipelines, 4-endpoint OpenAPI surface, top-3 sample pipeline + endpoint cards, and a README listing the actual P0 bugs the audit caught.

---

## v0.7 — 2026-05-07 (pre-release polish)

The release that turns the toolkit into a guided product.

**Interactive flow**:
- Phase 0 expanded: scope estimate → clarifying questions (`prompts/clarifying_questions.md`) → opt-in. The skill now asks about goal, skip-paths, known issues, sensitive paths, test posture, and budget before touching anything.
- Five new user-confirmation gates inserted between phases: **Gate A** (segment confirmation), **Gate B** (specialist + cost confirmation, the big cost gate), **Gate D** (post-review triage), and the existing Phase 7 opt-in. Each has an explicit prompt template the main agent uses.
- New `prompts/gap_handling.md` for post-review questions: triage, decisions only the user can make, pre-fix safety.

**Three new specialists**:
- `mobile-reviewer` — iOS / Android / RN / Flutter (lifecycle, permissions, native bridge, push, mobile secrets)
- `cli-tool-reviewer` — Click / Typer / Cobra / commander / clap (flag naming, exit codes, --json mode, stdout/stderr discipline)
- `test-suite-reviewer` — pytest / jest / vitest / playwright (mock hygiene, flake risk, coverage shape)

**Specialist coverage gaps**:
- New `specialist_gaps.json` output flagging segments where no specialist scored well. Default behavior: fall back to generalist + surface gap to user via `prompts/specialist_gap.md`. `--gap-threshold` tunable.

**Synthesis fix** (was the silent biggest issue):
- `scripts/synthesize.py` now actually reads the agent reports' content. Previously it only extracted file lists. Now it aggregates `Refactor suggestions`, `Concerns / smells`, and `Cross-segment hints` into `synthesis.json.agent_findings` — so the main agent can build the backlog from real signal instead of re-reading 30 reports manually.

**`--readonly` mode** (no project pollution):
- `run_pipeline.sh <root> --readonly` writes outputs to `~/.cartographer/<project-hash>/` instead of `<root>/.cartographer/`. Drop `_project.txt` marker for traceability.
- `CARTOGRAPHER_READONLY=1` env var equivalent.

**Schema cleanup**:
- Legacy v0.1 `prompts/segment_review.md` moved to `prompts/_archive/`. Single canonical schema is `specialist_base.md` + role file.

**Detector additions**: react_native, expo, flutter, ionic, capacitor, click, typer, argparse, cobra, commander, yargs, clap, oclif, pytest, unittest, jest, vitest, mocha, playwright, cypress, testing_library, hypothesis.

---

## v0.6 — 2026-05-06

- **Phase 7 — Apply backlog**: opt-in fix-application phase. New `prompts/fix_agent.md` and `scripts/apply_backlog.py`. Validated end-to-end on stocksCorrelation (3/3 fixes applied surgically).
- SKILL.md and run_pipeline.sh wired to detect `backlog.md` and prompt for Phase 7.

## v0.5 — 2026-05-06

- **Phase 1.6 — OpenAPI + per-endpoint deep call trace**:
  - `scripts/extract_openapi.py` (file / live / synthetic strategies)
  - `scripts/trace_endpoints.py` (deep BFS per endpoint with cross-endpoint reuse map)
- Better path-prefix matching for OpenAPI ↔ handler linkage.
- Recursive segment splitting (no more 155-file mega-segments).
- Per-segment relabeling so split sub-segments don't inherit parent integrations.
- Domain-aware consolidation (`_consolidate_to_domain`).
- Orphan singleton bundler (`_bundle_singletons_by_top_dir`).
- `__init__.py` filter extended to trivial `config.py`.

## v0.4 — 2026-05-06

- New specialist: `frontend-designer-reviewer` — visual polish, library recommendations (anime.js, GSAP, framer-motion, lottie, particles, three.js), Autonomous-vs-Needs-user-input tagging, Claude-design-limit awareness.

## v0.3 — 2026-05-06

- Function call graph extraction (Python AST-precise, JS/TS regex-best-effort).
- UML class diagram (`class_diagram.mmd`) with bases, methods, fields.
- Pipeline tracer (`scripts/trace_pipelines.py`): BFS from entry points through resolved call graph, per-pipeline Mermaid flowcharts.
- Scientific Python integration detectors: pandas, numpy, scipy, sklearn, yfinance, pyarrow, matplotlib, seaborn, torch, tensorflow, huggingface.
- TS path-alias resolver (parses `tsconfig.json`).
- New specialist: `data-pipeline-reviewer` (ETL/ML correctness — leakage, NaN, index alignment, perf, reproducibility).

## v0.2 — 2026-05-05

- Specialist agent library: 13 reviewer roles + matcher (`scripts/match_specialists.py`).
- `prompts/specialist_base.md` universal subagent contract.
- `agents/AGENTS.md` catalog.

## v0.1 — 2026-05-05

- Initial release.
- Phase 1 (map), Phase 2 (segment), Phase 3 (waves), Phase 4 (review), Phase 5 (synthesize), Phase 6 (final report).
- Single generic reviewer schema (`prompts/segment_review.md`, now archived).
