# Local reliability delivery — 14 October 2026

Branch: `feat/production-reliability`. Production deployment and data migration are reserved for the owner. No production data was changed.

Update: `feat/supabase-free-storage` adds PostgreSQL/pgvector and private Supabase Storage for Render Free without a disk. Follow [Supabase deployment](supabase-deployment.md) for the current free-hosting configuration; the disk/Chroma/R2 alternatives below remain supported. This change passed 77 focused local tests; live Supabase access remains an operator check.

Deployment follow-up: `feat/deployment-startup-fixes` removes the fatal bucket-size mismatch, enforces/displays the effective upload limit, validates credentials and pooler URLs early, groups static configuration errors, and permits private scratch fallback only with externally stored Supabase data. 102 focused tests passed. Invalid/public storage and ephemeral user-data configurations remain blocked; no secrets or production data were changed.

Research/UI follow-up: `fix/web-search-models-ui` excludes Gemini 3.6/3.8 Flash families from catalogs, cached fallback plans, OCR and direct calls; other verified free models remain eligible. Tavily uses Bearer authentication and basic search with automatic parameter upgrades disabled. Irrelevant document evidence routes to the original standalone question instead of inheriting an unrelated previous topic. Search errors/empty results are saved in the abstention answer and notes; reopened conversations restore warnings. Citation and grounding checks remain mandatory. The local Tavily key initially returned HTTP 401; after the owner replaced it, one live public football search returned five usable sources. Production credential validity is not inferred from that local result.

The composer wraps its model/fallback/relevance controls; user messages use an icon and preserve the exact message text without extra sender labels. Stream drafts reveal progressively between network batches, honor reduced motion and model resets, and give way to the accepted saved answer without a duplicate placeholder. 94 focused backend tests passed, frontend tests/typecheck/lint/production build passed, and the actual component preview fit desktop and 375px mobile widths without horizontal overflow. The authenticated production chat could not be inspected in the available browser; no saved messages were modified or stripped.

## Root causes and changes

Stable-answer follow-up: grouped citations such as `[W1, W2]` now pass exact ID membership checks and retain both sources at publication; unknown grouped IDs remain rejected. Generation and semantic validation explicitly distinguish uploaded documents from web pages, and the UI labels the cited source origin. Validation corrections keep the initial provisional draft visible and replace it once at final publication; initial provider failures still discard incomplete drafts. Bounded grounding retries and saved job checkpoints remain intact. The selector/refresh controls stay grouped, automatic mode has one option, and container queries place controls across rows on narrow screens. The jump-to-latest button is anchored above the composer rather than at a fixed page offset. 21 focused graph/job tests and 28 frontend tests passed, along with Ruff, ESLint and the frontend production build. Desktop and 375px previews had no horizontal overflow. No production provider calls or saved-data edits were performed in this follow-up.

| Finding | Implementation |
| --- | --- |
| Three attempts included repeated attempts on one model, starving later models | Every compatible distinct model is considered before a bounded retry pass. Attempts share a deadline; each attempt reserves time for remaining candidates. |
| Model health and successful selection existed only in process memory | SQL-backed project ledger, task-specific health, cooldowns, latency, request/token reservations, concurrency leases and conversation affinity. PostgreSQL supports shared routing across instances; SQLite requires one durable service. |
| 429 is quota exhaustion; replacing a key in the same project cannot reset it | Project-scoped accounting, conservative configurable budgets, cooldowns and bounded Retry-After handling. Model-level quota state is shared across tasks. Extra JSON fallback calls also reserve quota. |
| 503 and transport timeouts are provider/service failures | Distinct fallback, bounded retries with backoff and jitter, deadline cancellation and clear interruption messages. Code cannot guarantee Google's availability. |
| Browser disconnect cancelled backend research | Database-backed jobs continue independently of SSE clients. Completed LangGraph node snapshots, evidence, history and events are retained. Authorized event replay, cancellation and retry resume the next unfinished node. |
| Client fallback overwrote the user's selected model | Selected and actual models are separate. Strict selection and automatic fallback are exposed in the UI. |
| SQLite metadata, Chroma vectors and local uploads defaulted to a local directory | Production startup refuses unmounted ephemeral storage unless PostgreSQL, external Chroma and R2 are configured together. No files are moved automatically. |
| Legacy workspaces have no owner | Local read-only inspection found two unowned workspaces. They remain hidden and preserved. Recovery requires confirmation of ownership and an explicit operator action. |
| Frozen development environment installed unused heavyweight packages in production | `pyproject.toml` plus `uv.lock` replace all requirements files. Docker excludes dev and local embedding extras. CPU embeddings remain available with `--extra local`. |
| Embedding requests used document task mode for queries, and SDK defaults could use Vertex or hidden retries | Query embeddings use `embed_query`, retaining the existing 768-dimensional index. The Developer API client uses explicit timeout and no SDK retries. |
| OCR guessed retired fallback IDs | OCR discovers verified free models and uses the bounded router; it does not invent fallback IDs. |

Gemini discovery intersects authenticated Models.list with official free input/output pricing. Capability routing additionally permits only reviewed model families and enforces context/output limits. A listing is **not** proof that generation will succeed for a project; runtime errors update health. Production requires an explicit confirmation that project billing is disabled. That flag is an operator assertion, not an API billing audit.

References: [Google quota scope](https://ai.google.dev/gemini-api/docs/rate-limits), [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), [Render storage persistence](https://render.com/docs/disks), [Render Docker caching](https://render.com/docs/docker).

## Verification evidence

- Full local backend regression suite: **133 passed** with isolated databases and mocked providers, including sticky routing across store instances, quota/concurrency reservations, authorization, saved-job idempotency, cross-session data access, retry without repeated retrieval, and production configuration checks.
- Frontend: **21 tests passed**, TypeScript and ESLint passed, Next.js production build passed with standalone output.
- Final retrieval/OCR changes: **26 focused tests passed**; backend Ruff and lock consistency checks pass. No additional full-suite rerun was performed after these changes.
- Local SQLite was inspected read-only: integrity `ok`; 5 workspaces, 5 documents, 9 conversations, 21 messages, 14 workflow runs. Two workspaces are unowned; two distinct owned identities are present. No ownership assignments or migrations were executed against this database.
- Legacy dependency freeze: 147 packages. Exported production lock: 126 packages across supported platforms. The 26 excluded legacy packages include Torch, Transformers, Sentence Transformers, SciPy, scikit-learn, OpenAI, top-level LangChain, pytest and Ruff. Five platform/shared-database packages are added. Actual installed counts differ by platform. Chroma's required ONNX, tokenizers, Kubernetes and build dependencies are retained.

## Remaining verification

Docker is not installed on this computer: image startup, container memory and before/after build-time benchmarks are **not measured**. No speedup percentage is claimed. Dependency-layer caching and smaller production dependency selection are implemented, not benchmarked here. Versioned base-image tags should be resolved to reviewed digests before a production release.

Physical laptop/phone sessions, production Clerk application alignment, production backups, Render disk configuration and PostgreSQL/remote-Chroma integration are not verified here. Tests prove local persistence and isolation with controlled identities, plus real Clerk JWT signature/expiry/origin validation. The public Render health request timed out after 40 seconds; this is not proof of a specific production fault.

## Local commands

```powershell
cd backend
# Use the standalone uv CLI, or the already installed .venv/Scripts/uv.exe.
uv sync --frozen
uv run --no-sync pytest
uv run --no-sync ruff check app tests
# Optional offline CPU embedding profile:
uv sync --frozen --extra local
uv run --no-sync python -m app.bootstrap
```

For Docker, copy the environment examples into ignored local env files, then run from the repository root:

```powershell
docker compose -f docker.yml up --build backend
# Optional local frontend image; public Clerk key is required during its build.
docker compose --env-file frontend/.env.local -f docker.yml --profile frontend up --build
```

The named `crebry-data` volume is a separate dataset. Existing `backend/data` is never automatically copied into it or overwritten. Stop the old backend first if using the same ports. Preserve the volume; do not use `down -v` for data you need. Vercel frontend hosting can remain unchanged.

## Configuration, recovery and rollback

Set the same Clerk application on frontend and backend; configure `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES` and `FRONTEND_ORIGIN`. Ownership always comes from the verified token's `sub`, never from client input or session/device IDs.

For production, configure `ENVIRONMENT=production`, the actual `GEMINI_PROJECT_ID`, billing-disabled confirmation, and quota budgets at or below AI Studio's project/model limits. Defaults are conservative application limits, not a claim about Google's current allocation. Keep one Gemini project ID across key rotation. Configure a durable `DATA_DIR` under `PERSISTENT_DATA_ROOT`, or PostgreSQL (`DATABASE_URL`), protected remote Chroma and R2. A Render persistent disk supports one service instance; horizontal scaling requires external metadata and vector storage. No paid resource is provisioned by this branch.

Before any production change, stop writes and take a verified SQLite backup using SQLite's backup API (not a live copy of only the WAL database file), plus the complete Chroma directory and original uploads. For PostgreSQL, use an appropriate database backup. Check ownership counts and indexes before and after moving a backup to durable storage. New routing/job/rate-limit tables are additive; old rows and nullable legacy ownership remain unchanged.

To recover an unowned workspace, verify its owner and Clerk ID first, stop the backend, then explicitly run `scripts.claim_legacy user_CONFIRMED_ID --workspace CONFIRMED_WORKSPACE_ID`. The existing script backs up SQLite and refuses reassignment of owned workspaces. Do not use a blanket claim for data with uncertain ownership. No recovery has been executed in this task.

Rollback by stopping new workers, retaining storage/backups, and checking out the prior application revision with its matching dependencies. Additional tables can remain; do not drop them. Old code will not resume the new jobs, but saved user messages and published answers remain in the original tables. Do not clear storage or reset ownership to make rollback appear successful.

Job retries are idempotent for the same request key. A process crash can repeat its in-flight node if completion happened before its checkpoint committed. Completed checkpointed nodes are not restarted. Failed jobs require explicit retry; provider streams themselves cannot resume mid-token. Persisted event/snapshot retention requires an operator policy before large-scale use; this branch does not delete history.
