# Clarifying questions — Phase 0 expansion

After the initial scope estimate, the main agent asks the user a small set of clarifying questions before doing anything else. The goal is to **focus** the audit and avoid wasting tokens on areas the user doesn't care about.

Use **AskUserQuestion** if available; otherwise format as a single message asking for a one-shot reply.

## Questions to ask

Pick the most relevant 3–5 from this list. Don't overwhelm — a 10-question intake is worse than a 3-question one.

### Always ask

1. **Goal**:
   > What's the primary goal of this audit? Pick one (or describe):
   > - Security audit (auth, secrets, injection surfaces)
   > - Refactor planning (find duplication, centralization wins)
   > - Onboarding doc (understand the structure end-to-end)
   > - Health check (general code-quality sweep)
   > - Pre-release / pre-merge review
   > - Something else?

2. **Skip list**:
   > Are there directories or paths I should **skip**? (vendored libs, generated code, legacy modules, archived experiments) — I'll exclude them from the review.

### Ask when relevant

3. **Known issues** (if user mentioned bugs / pain points already):
   > You already mentioned `<X>`. Is there anything else you already know is broken? I'll de-prioritize finding what you already know.

4. **Ground-truth docs** (if API project detected):
   > Do you have an OpenAPI spec, architecture diagram, or design doc I should treat as source of truth? Path/URL?

5. **Style preferences** (if mixed conventions detected at scope phase):
   > Quick scan shows mixed conventions (e.g. snake_case + camelCase). Is one of them the standard you want enforced, or are you genuinely cross-runtime?

6. **Sensitive paths**:
   > Any paths containing **proprietary algorithms** or sensitive logic that you'd rather I describe at a higher level instead of inventorying line-by-line? (Specialist reports will redact symbol names in those paths.)

7. **Test posture** (if `tests/` directory present):
   > Should test code be reviewed (test quality) or only used as a signal of intent (don't review the tests, but use them to understand what each module is supposed to do)?

8. **Time / cost budget**:
   > Soft cap on token spend? Affects whether I run all segments (heavier) or top-N by complexity (lighter).

## How to use the answers

Translate user answers into:

- **`scope.json`** at `.cartographer/scope.json`:
  ```json
  {
    "goal": "refactor planning",
    "skip_paths": ["vendored/", "legacy/", "**/migrations/old_*"],
    "known_issues": ["Auth flow has a bug we're already fixing in #123"],
    "ground_truth": "docs/architecture.md",
    "style_standard": "snake_case",
    "sensitive_paths": ["src/strategies/proprietary/"],
    "test_posture": "review",
    "budget_hint": "medium"
  }
  ```
- The mapper / segmenter respect `skip_paths` (re-run with `--exclude` flag derived from this).
- The specialist matcher uses `goal` to break ties: a security-focused audit boosts `auth-security-reviewer`, etc.
- Specialist subagents are told about `known_issues` and `sensitive_paths` so they don't re-flag.
- The final report annotates findings with goal-relevance.

## Tone

- One short message with all questions inline. Don't ping-pong.
- Number the questions. Tell the user they can answer just the ones they care about.
- Default to sensible behavior if user replies "go" without answering — don't block on perfect input.

## Example one-shot phrasing

> Before I run the audit, four quick questions to focus it (answer the ones that matter; "go" with no answers means I'll use sensible defaults):
>
> 1. **Goal**: security audit, refactor planning, onboarding doc, or health check?
> 2. **Skip**: any paths I should exclude (vendored deps, legacy modules)?
> 3. **Known issues**: anything you already know is broken so I don't waste time re-finding it?
> 4. **Budget**: rough token cap, or "no limit"?
