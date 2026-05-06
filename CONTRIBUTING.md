# Contributing to project-cartographer

Thanks for your interest! Cartographer is a Claude Code skill that audits large codebases — and it has a lot of small, well-bounded extension points (specialist roles, integration detectors, language parsers). Contributions of all sizes are welcome.

## New here? Start with a Good First Issue

We curate beginner-friendly issues that come with the relevant files, rough scope, and a suggested approach:

**[Browse Good First Issues](https://github.com/roeimichael/project-cartographer/labels/good%20first%20issue)**

Good entry points:
- Add a new specialist reviewer (one markdown file in `agents/`)
- Add an integration detector (one regex pattern in `scripts/map_project.py`)
- Add a verified entry to `agents/_registry.yml` (skills.sh package mapping)

## Understanding the architecture

Cartographer runs a multi-phase pipeline. Deterministic work is scripts; judgment work is subagents.

```
Phase 0    Scope & user opt-in                       (Claude — interactive)
Phase 1    Build dep + call + class graph            (script)
Phase 1.5  Trace pipelines from entry points         (script)
Phase 1.6  OpenAPI + per-endpoint deep call trace    (script)
Phase 2    Detect & label functional segments        (script)
Phase 3    Plan review waves                         (script)
Phase 3.5  Match a specialist to each segment        (script)
Phase 4    Dispatch review subagents (≤5 per wave)   (Claude)
Phase 5    Synthesize cross-cutting findings         (script + Claude)
Phase 6    Final report + refactor backlog           (Claude)
Phase 7    Apply backlog fixes (opt-in)              (Claude + script)
```

**Recommended reading order for new contributors:**
1. `SKILL.md` — top-level entry point Claude Code reads
2. `scripts/map_project.py` — Phase 1, the foundation graph
3. `scripts/classify_segments.py` — Phase 2, where segmentation lives
4. `scripts/match_specialists.py` — Phase 3.5, scoring logic
5. `agents/AGENTS.md` + a couple specialist files (e.g. `agents/data-pipeline-reviewer.md`) — the agent contract
6. `prompts/specialist_base.md` — the universal subagent schema

For a deeper customization guide see [`docs/customization.md`](docs/customization.md).

## Getting started

### Prerequisites

- Python 3.11+
- Claude Code (for running Phases 4 and 7)

### Development setup

```bash
git clone https://github.com/roeimichael/project-cartographer.git
cd project-cartographer

# Optional but recommended (gitignore-aware walking, networkx, fuzzy matching)
pip install -r requirements.txt

# Run the scripted phases on any project
./run_pipeline.sh /path/to/your/repo

# Or against a sample project
./run_pipeline.sh /path/to/your/repo --readonly   # output goes to ~/.cartographer/<hash>/
```

### Project structure

```
project-cartographer/
  SKILL.md                  # Claude Code skill entry point
  run_pipeline.sh           # convenience runner for scripted phases
  agents/
    *-reviewer.md           # 17 specialist roles with YAML frontmatter
    AGENTS.md               # catalog
    _registry.yml           # skills.sh package mapping (mostly empty)
  prompts/
    specialist_base.md      # universal subagent contract
    fix_agent.md            # Phase 7 fix subagent prompt
    clarifying_questions.md # Phase 0 user Q&A template
    gap_handling.md         # post-review user Q&A template
    specialist_gap.md       # Phase 3.5 coverage-gap surfacing
    final_synthesis.md      # Phase 6 final-report template
    _archive/               # legacy schemas
  scripts/
    map_project.py          # Phase 1 — dep + call + class graph
    trace_pipelines.py      # Phase 1.5 — BFS from entry points
    extract_openapi.py      # Phase 1.6 — OpenAPI extraction
    trace_endpoints.py      # Phase 1.6 — per-endpoint deep trace
    classify_segments.py    # Phase 2 — connected components + split + consolidate
    plan_waves.py           # Phase 3 — topological wave ordering
    match_specialists.py    # Phase 3.5 — score & assign specialists
    synthesize.py           # Phase 5 — read reports, aggregate findings
    apply_backlog.py        # Phase 7 — fix dispatch planner
    finalize_fixes.py       # Phase 7 — pre/post (branch + diff + test)
    install_specialist.py   # opt-in skills.sh installer
    _progress.py            # heartbeat helper
    cartographer_status.py  # read-side progress viewer
    resolve_output_dir.py   # --readonly resolver
  examples/
    stocksCorrelation/      # real curated outputs from a sample run
  docs/
    customization.md        # how to extend specialists / detectors / languages
```

## Common contributions

### Adding a specialist reviewer

1. Drop `agents/<name>-reviewer.md` with YAML frontmatter:
   ```yaml
   ---
   name: <name>-reviewer
   description: One-line role summary
   priority: 1000
   triggers:
     integrations: [foo, bar]
     paths: ["foo/", "src/bar"]
     filenames: ["*.foo"]
   ---
   ```
2. Body follows the contract in `prompts/specialist_base.md`.
3. The matcher auto-discovers it — no scripted registration needed.
4. Add a row in `agents/AGENTS.md` and the README's specialist table.

### Adding an integration detector

Edit `scripts/map_project.py` — the `INTEGRATION_PATTERNS` dict. One regex per integration label. Test on a real project that uses it.

### Adding a language

`docs/customization.md` walks through the parser interface. Today we have AST-precise Python and regex-best-effort JS/TS/Go. Tree-sitter for non-Python is a roadmap item; PRs welcome.

## Submitting changes

1. Fork
2. Branch (`git checkout -b feature/my-feature`)
3. Run the pipeline on at least one sample project before/after your change — make sure outputs are sensible (no segment regressions, no new errors)
4. Commit with a clear message describing what and why
5. Open a PR against `main`

### PR guidelines

- Keep PRs focused — one feature or fix per PR
- For changes to scripts, include a before/after of the relevant output (segment counts, endpoint linkage, etc.) when behavior changes
- Update `CHANGELOG.md` for user-visible changes
- Update `README.md` if you add a user-facing feature or specialist

## Reporting bugs

Open an issue with:
- What you expected vs. what happened
- The project you ran it on (anonymized OK), or steps to reproduce on a sample
- Output of `python scripts/cartographer_status.py` if a phase hung
- Your Python version and OS

## License

By contributing, you agree your contributions will be licensed under the MIT License.
