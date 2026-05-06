# project-cartographer

[![CI](https://github.com/roeimichael/project-cartographer/actions/workflows/ci.yml/badge.svg)](https://github.com/roeimichael/project-cartographer/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2)](https://claude.com/claude-code)

> Map, audit, and refactor a 1000-file codebase the way a senior engineer would — but with 17 specialist reviewers running in parallel.

A **Claude Code plugin** that builds a dependency + call graph, segments the repo by integration / domain, dispatches per-segment specialist reviewers in waves of ≤5, synthesizes findings into a P0–P3 refactor backlog, and optionally applies surgical fixes behind a confirmation gate.

## Install

```bash
# Inside Claude Code:
/plugin install roeimichael/project-cartographer
```

Or clone into your Claude Code plugins directory directly.

## Use

```
/cartographer:audit              # full pipeline — graph → segments → review → backlog → fixes
/cartographer:map                # graph + diagrams only, no review (cheap, no LLM cost)
```

Or just say it in plain English — the skill triggers on phrases like *"audit this project"*, *"map out my codebase"*, *"find duplication across the repo"*.

The plugin walks you through scope → clarifying questions → segment confirmation → cost estimate → review → backlog → fixes, asking before any expensive step.

## What you get

- **Dependency + call graph + class hierarchy** (Python AST-precise, JS/TS/Go regex-best-effort)
- **Pipeline traces** from entry points (API handlers, `main()`, workers) — one Mermaid flowchart per pipeline
- **OpenAPI extraction + per-endpoint deep call trace** with cross-endpoint reuse map
- **17 specialist reviewers**: auth-security, supabase, db-schema, telegram-bot, ai-pipeline, backend-api, data-pipeline, queue-worker, webhook-integration, frontend-ui, frontend-designer, mobile, cli-tool, test-suite, file-storage, realtime-streaming, devops-config, caching, generalist
- **Cross-cutting synthesis** — duplication, naming drift, centralization candidates
- **Refactor backlog** ranked P0–P3
- **Fix application** (opt-in, behind a gate) — branch isolation, surgical edits, test runner

## Pipeline

```
Phase 0    Scope & opt-in                            (interactive)
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

Phases 1 → 3.5 are deterministic Python (~30s for 300 files, no LLM cost). Only Phase 4 and 7 spend subagent invocations. A 1000-file repo with 20 segments costs ~20 subagent calls, not 1000 file reads.

## Run scripted phases standalone (no Claude Code)

For CI or to just get the diagrams:

```bash
pip install pathspec networkx rapidfuzz
bash run_pipeline.sh /path/to/your/repo            # writes to <repo>/.cartographer/
bash run_pipeline.sh /path/to/your/repo --readonly # writes to ~/.cartographer/<hash>/
```

## Languages

- **Python** — AST-precise (full call graph + class hierarchy with bases/methods/fields)
- **JavaScript / TypeScript** — regex-based, best-effort (TS path aliases resolved)
- **Go** — regex-based, best-effort

Tree-sitter for non-Python is on the roadmap.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

PRs welcome. Open an issue first for non-trivial changes — the [issue templates](.github/ISSUE_TEMPLATE/) cover bug reports and feature requests. New specialist reviewers are the easiest contribution: drop a markdown file under `agents/` with YAML frontmatter and the matcher auto-discovers it.
