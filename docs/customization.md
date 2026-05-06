# Customization

Things you might want to extend.

## 1. Add a new integration detector

Open `scripts/map_project.py` and add an entry to the `INTEGRATIONS` dict:

```python
INTEGRATIONS = {
    # ...existing entries...
    "my_service": [
        r"\bmy_service\b",            # imports / mentions
        r"@myservice/sdk",             # npm packages
        r"MyServiceClient\(",          # constructor calls
    ],
}
```

Patterns are case-insensitive Python regex. The label becomes part of segment names (e.g. `my_service@src/integrations/`).

## 2. Add a new language

Currently: Python (precise, AST), JS/TS/Go (regex). To add a language, do two things in `map_project.py`:

**a. Extend `SUPPORTED_EXT`:**
```python
SUPPORTED_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs"}
```

**b. Add a parser function** that takes `(rel_path, src, pmap)` and returns a `FileNode`. It must:
- Populate `node.imports` (list of import strings)
- Append `Symbol` records to `pmap.symbols` (functions/classes with file + line)

Then dispatch to it in `main()`:

```python
elif ext == ".rs":
    node = parse_rust(rel_str, src, pmap)
```

For non-trivial languages, consider switching to tree-sitter — the regex approach works for JS/TS/Go because their syntax is regular enough, but it will struggle on languages with macros or significant whitespace ambiguities.

## 3. Add a new endpoint framework

Endpoint detection lives in `ENDPOINT_PATTERNS`:

```python
ENDPOINT_PATTERNS = [
    # (compiled_regex, framework_label)
    (re.compile(r"router\.handle\(['\"]([^'\"]+)['\"]"), "my_framework"),
]
```

The first capture group should be the path. If the framework encodes method differently (e.g. file-based routing), follow the `nextjs` example in `scan_endpoints_and_integrations` — that pattern infers method from the function name and path from the file location.

## 4. Tweak the synthesis findings

`scripts/synthesize.py` currently checks four things. Add a fifth by:

1. Defining the analysis (input: `seg_symbols`, `pmap`; output: a list of finding dicts).
2. Adding the result to the `synth` dict under a new key.
3. Extending `render_markdown()` to render it.

Example: detect functions with very long names (smell):

```python
long_names = [
    {"file": s["file"], "name": s["name"], "length": len(s["name"])}
    for syms in seg_symbols.values() for s in syms
    if s["kind"] == "function" and len(s["name"]) > 40
]
synth["long_names"] = long_names
```

## 5. Tweak segment splitting

By default, segments larger than 40 files get split (so a single review subagent doesn't get an unbounded file list). Override with `--max-files-per-segment` on `classify_segments.py`. Going too small (<15) creates segment fragmentation; too big (>60) overloads subagents.

## 6. Adjust wave size

Default is 5 parallel agents per wave. Override with `--wave-size` on `plan_waves.py`. Lower it (3) for very large repos to stay under context budget; raise it (8) only if you have plenty of headroom.

## 7. Add a specialist reviewer

Drop a new file `agents/<name>-reviewer.md` with this frontmatter shape:

```markdown
---
name: my-specialist-reviewer
description: One-line role description. Used by the matcher and shown to the user.
triggers:
  integrations: [my_integration_a, my_integration_b]
  file_patterns: ["**/my_dir/**", "**/*.myext"]
  endpoint_count_min: 0
priority: 75
---

# my-specialist-reviewer

## Specialist focus
What this reviewer focuses on, in 1–3 sentences.

## What to flag
- Bullet list of things this specialist looks for.
- Reference file:line.

## Cross-segment hints to surface
- Things to flag for the synthesizer to relocate.

## Output additions
A specialist-specific subsection added under "Specialist findings" in the report.
```

The matcher (`scripts/match_specialists.py`) auto-discovers it on next run. **Priority guidelines:**

- `90–100`: security/data-correctness specialists (auth, supabase RLS).
- `80–89`: integrations with strict contracts (db schema, telegram, ai pipelines, backend APIs).
- `70–79`: cross-cutting infra (devops, webhooks, frontend, file storage).
- `60–69`: ergonomic concerns (caching).
- `0`: the generalist fallback. Don't reuse this unless replacing the fallback.

Update `agents/AGENTS.md` to add a row for the new specialist (the catalog is curated, not auto-generated).

## 8. Override specialist assignment per segment

After Phase 3.5, `wave_plan.json` contains `specialist_assignments`. To force a different specialist for a segment, edit the JSON before Phase 4:

```json
"specialist_assignments": {
  "auth_module": {
    "assigned_agent": "auth-security-reviewer",
    "score": 4750,
    "runners_up": [...]
  }
}
```

Change `assigned_agent` to any specialist name listed in `specialist_index`. The dispatcher will use the override.
