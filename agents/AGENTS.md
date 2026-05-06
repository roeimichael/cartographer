# Specialist agent catalog

Each segment in your project gets reviewed by **one specialist** picked by `scripts/match_specialists.py` based on the segment's detected integrations and file patterns. The specialist with the highest matching `priority` wins; if nothing matches, `generalist-reviewer` is the fallback.

You can override per-segment matches manually — see `docs/customization.md`.

## Catalog

| Specialist | Triggers (integrations) | File patterns | Priority | Focus |
|------------|-------------------------|---------------|----------|-------|
| [auth-security-reviewer](auth-security-reviewer.md) | nextauth, clerk, auth0, passport, jose, jsonwebtoken, authlib, descope | auth/, middleware/, security/, session*/ | 95 | Authn, authz, tokens, sessions, secrets |
| [supabase-reviewer](supabase-reviewer.md) | supabase | supabase/, *.sql | 90 | Client, RLS, edge functions, realtime, storage |
| [db-schema-reviewer](db-schema-reviewer.md) | postgres, mongodb, mysql, sqlalchemy, prisma, drizzle, typeorm, mongoose | migrations/, models/, schema.*, *.sql, db/, database/ | 85 | Schema, migrations, indexes, drift, raw SQL |
| [telegram-bot-reviewer](telegram-bot-reviewer.md) | telegram | bot/, handlers/, telegram/ | 85 | Handlers, FSM, webhook security, rate limits |
| [ai-pipeline-reviewer](ai-pipeline-reviewer.md) | openai, anthropic, cohere, voyage, langchain, llamaindex, mistral, gemini | ai/, llm/, agent*/, prompts/, rag/ | 85 | Models, prompts, caching, budgets, structured output |
| [backend-api-reviewer](backend-api-reviewer.md) | fastapi, flask, express, hono, koa, nestjs, gin, echo | routes/, api/, handlers/, controllers/ | 80 | Endpoints, validation, auth posture, response shapes |
| [data-pipeline-reviewer](data-pipeline-reviewer.md) | pandas, numpy, scipy, sklearn, yfinance, pyarrow, matplotlib, seaborn, torch, tensorflow, huggingface | dataio/, data/, features/, modeling/, training/, backtest*/, evals/, pipelines/ | 80 | ETL/ML correctness, leakage, NaN/index, perf, reproducibility |
| [queue-worker-reviewer](queue-worker-reviewer.md) | celery, rq, bullmq, rabbitmq, kafka, sqs, redis | workers/, jobs/, tasks/, consumers/, celery*/ | 80 | Idempotency, retries, DLQ, backpressure |
| [webhook-integration-reviewer](webhook-integration-reviewer.md) | stripe, github, twilio, sendgrid, resend, webhook | webhooks/, integrations/, clients/ | 80 | Sig verification, replay, outbound timeouts |
| [frontend-designer-reviewer](frontend-designer-reviewer.md) | react, nextjs, vue, svelte, solid | pages/, app/, layouts/, App.*, marketing/, landing/, hero/, sections/ | 78 | Visual polish, motion, library recs (anime.js, GSAP, lottie, particles, three.js); flags user-intervention items |
| [mobile-reviewer](mobile-reviewer.md) | react_native, expo, flutter, swift, swiftui, kotlin, jetpack_compose, ionic, capacitor | *.swift, *.kt, *.dart, ios/, android/, App.tsx, App.js, expo/, _layout.tsx | 78 | Lifecycle, permissions, native bridge, list perf, push, deep links, mobile secrets |
| [cli-tool-reviewer](cli-tool-reviewer.md) | click, typer, argparse, cobra, commander, yargs, clap, oclif | cli/, cmd/, bin/, scripts/, console/ | 78 | Flag naming, exit codes, --json mode, stdout/stderr discipline, idempotency |
| [test-suite-reviewer](test-suite-reviewer.md) | pytest, unittest, jest, vitest, mocha, playwright, cypress, testing_library, rtl, hypothesis | tests/, test/, __tests__/, *_test.py, test_*.py, *.test.ts/tsx/js, *.spec.ts/tsx/js, conftest.py | 72 | Mock hygiene, flake risk, no-assertion smell, coverage shape, fixture sharing |
| [frontend-ui-reviewer](frontend-ui-reviewer.md) | react, nextjs, vue, svelte, solid | *.tsx, *.jsx, *.vue, *.svelte, components/, pages/, app/ | 75 | Hooks, props, state, render perf, a11y |
| [file-storage-reviewer](file-storage-reviewer.md) | s3, gcs, azure_blob, supabase_storage, vercel_blob, filesystem | storage/, uploads/, files/, blob/ | 75 | Upload safety, signed URLs, MIME, FS leaks |
| [realtime-streaming-reviewer](realtime-streaming-reviewer.md) | websocket, socketio, sse, pusher, ably, pubnub, supabase_realtime | realtime/, ws/, socket*/, sse/ | 70 | Channels, broadcast scope, auth-per-message |
| [devops-config-reviewer](devops-config-reviewer.md) | vercel, railway, fly, docker, kubernetes, github_actions | Dockerfile*, docker-compose*, .github/workflows/, k8s/, vercel.json, railway.toml, fly.toml, .env* | 70 | Image hygiene, secrets, env drift, pins |
| [caching-reviewer](caching-reviewer.md) | redis, memcached, ioredis, swr, react_query, next_cache | cache/, redis/ | 65 | TTL, invalidation, stampede, key collisions |
| [generalist-reviewer](generalist-reviewer.md) | (any) | * | 0 | Cohesion, deletability, generic smells |

## How matching works

For each segment, `match_specialists.py`:

1. Scores every specialist against the segment:
   - `+50` per integration overlap
   - `+10` per file-path glob hit (files in the segment that match the specialist's `file_patterns`)
   - `+endpoint_count_min × 5` if the specialist requires endpoints and the segment has them
2. Multiplies the score by the specialist's `priority`.
3. Picks the highest non-zero score; falls back to `generalist-reviewer` on a tie at zero.
4. Writes the assignment to `wave_plan.json` as `assigned_agent` per segment.

## Adding a specialist

1. Drop a new `agents/<name>-reviewer.md` with frontmatter (see existing files).
2. The matcher auto-discovers it on next run.
3. Add an entry here in the catalog.
4. If the specialist needs new integrations detected, also add them to `scripts/map_project.py`.

See [`docs/customization.md`](../docs/customization.md) for the full extension guide.
