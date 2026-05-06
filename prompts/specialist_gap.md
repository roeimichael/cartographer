# Specialist coverage gap — main-agent prompt

After Phase 3.5, if `.cartographer/specialist_gaps.json` is non-empty, surface the gaps to the user **before** Phase 4 dispatch (this is part of GATE B).

## What a gap means

A "gap" segment is one where:
- The matcher's top score fell below the threshold (default 1500), **or**
- The segment fell back to `generalist-reviewer` despite having >5 files

Both indicate the skill's installed specialist library doesn't cover this segment well. Dispatching `generalist-reviewer` is a valid fallback but produces a less focused review.

## What to ask the user

Format the gap list clearly. Don't bury it in prose:

> Three segments don't fit any installed specialist well — they'll fall back to `generalist-reviewer` unless you intervene:
>
> | Segment | Files | Detected | Score | Best alternative |
> |---------|-------|----------|-------|------------------|
> | `solana@src/blockchain` | 12 | solana, web3 | 700 | `generalist-reviewer` |
> | `graphql@src/api/gql` | 8 | graphql, apollo | 1100 | `backend-api-reviewer (1100)` |
> | `infra/terraform` | 6 | hcl, terraform | 90 | `devops-config-reviewer (200)` |
>
> Options:
>
> 1. **Use generalist for all gaps** (simplest — review still happens, just less focused)
> 2. **Use the runner-up specialist** for each gap (e.g. `backend-api-reviewer` for the GraphQL one — overlaps in scope)
> 3. **Skip these segments** in Phase 4 (cheaper but they don't get reviewed)
> 4. **Install matching specialists from skills.sh** *(if dynamic install is enabled — see below)*
> 5. **Custom**: specify per-segment

## When skills.sh dynamic install IS enabled

If `agents/_registry.yml` is populated AND the user said "yes, allow installs" (gate on `--allow-skill-install`), additionally show:

> I can install matching specialists from skills.sh. From `agents/_registry.yml`:
> - `graphql` → `graphql-api-reviewer` (verified: ?)
> - `solana` → `solana-reviewer` (verified: ?)
>
> Reply **"install graphql,solana"** to fetch them. I'll run:
>   `python scripts/install_specialist.py --integrations graphql,solana --execute --allow-skill-install`
>
> Each install is logged to `.cartographer/specialist_install.log`. After install, re-run `match_specialists.py` to pick them up.

**Important honesty**: the registry ships mostly empty because skills.sh package names shift and we don't auto-discover them. If a user asks to install something not in the registry, tell them and offer to add it manually.

## When skills.sh is NOT enabled

Don't mention the install option — keep it to options 1-5 above. The user can still install specialists manually from skills.sh marketplace and re-run; just don't volunteer the suggestion when dynamic install is off.

## Recording the user's choice

Save the resolution to `.cartographer/specialist_gap_resolution.json`:

```json
{
  "resolution": "use_runners_up",
  "per_segment": {
    "solana@src/blockchain": {"agent": "generalist-reviewer"},
    "graphql@src/api/gql": {"agent": "backend-api-reviewer"},
    "infra/terraform": {"agent": "skip"}
  }
}
```

Then update `wave_plan.json.specialist_assignments` to reflect the choice before Phase 4 dispatches.

## Tone

- Don't apologize for the gap. The library is finite — having gaps is normal.
- Don't push the user to install. Generalist works.
- Keep it short. Three sentences + a table + numbered options.
