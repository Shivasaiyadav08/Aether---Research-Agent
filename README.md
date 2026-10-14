# Crebry — The Research Agent

A personal research workspace with Clerk sign-in, account-owned workspaces, local or Gemini
embeddings, persistent Chroma, and a real LangGraph corrective RAG workflow.


- A public landing page explains the project; `/research` requires sign-in.
- Clerk manages sign-up, sign-in, and account controls. FastAPI verifies session
  signatures and allowed origins and checks workspace ownership on every resource.
- Workspaces belong to individual Clerk users. Documents, chats, sources, and
  traces inherit the workspace boundary. Other users receive 404.
- Settings and the Agent Workflow page were removed. Research and Knowledge
  remain, with actual evidence and a compact inspectable graph in Intelligence.
- Choose a free model in the chat composer before asking. The server accepts only
  Gemini text models with published free-tier input/output pricing and key access.
- Set the minimum document relevance beside the model picker (0–100%, default
  50%). The choice applies to new questions and regeneration during the current
  signed-in session; a reload or account reset returns it to 50%. Higher values
  accept fewer chunks. This is a per-chunk score cutoff, not answer confidence.
- The landing-page example shows the model and relevance controls. Preferences
  shares the same cutoff, and Intelligence records the cutoff used for each run.
- Retrieved chunks are graded together in one structured request. Citation prompting includes an
  explicit format example; citation and grounding checks remain enabled.
- If the chosen model is unavailable, a real event explains the switch to a free
  fallback. Candidates have bounded attempts; no paid-only model is used.

## Features

PDF, DOCX, UTF-8 TXT and Markdown uploads; measured transfer progress; extraction;
800-character chunks with 150 overlap; local embeddings; workspace isolation;
hash-based duplicates; filename search; preview; original download; delete;
staged reindex; streaming Markdown; clickable document/web citations; copy;
latest-question regeneration; SQLite history and traces; light/dark toggle.

The graph retrieves, grades, separately assesses sufficiency, conditionally
rewrites/searches Tavily, generates, validates, and finalizes. A rejected answer
can regenerate once. Streaming drafts are provisional until accepted.
The relevance control is disabled while research runs. It changes only that
request's grading cutoff; sufficiency checks, grounding validation, and shared
server defaults remain unchanged. API clients can send `relevance_threshold`
between 0 and 1 in `/api/chat/stream`; omitting it retains the server default.

Research continues when you switch between Research and Documents, visit another
app page through its links, or switch browser tabs. Return to Research to see the
ongoing draft or completed answer. Stop requests cancellation of the saved backend job; signing
out or changing accounts detaches the browser and clears private state. Backend jobs continue; reopen the saved conversation to resume progress after a reload or disconnect.

## Local reliability and Docker

See [the reliability report](docs/reliability-report.md) for verified changes, `docker.yml` usage, dependency profiles, storage requirements, safe recovery and rollback. Docker builds install the frozen `uv.lock` production profile; development tools and local CPU embeddings are excluded.

## Setup on this Windows computer

The Python virtual environment already exists at `backend/.venv`. Its runtime is
Python 3.12.14 from the Codex desktop bundle because the Windows Python launcher
was unavailable. Use its executable directly; activation is optional.
For another machine, install Python 3.12 and Node.js 24 LTS, recreate the venv,
use `uv sync --frozen` in backend, and run `npm ci` in frontend. Backend dependencies are defined in `pyproject.toml` and pinned in `uv.lock`.

### 1. Connect Clerk

For this project's linked application, the Clerk CLI can write the keys directly
without copying them into chat. Run these commands from `frontend`:

```powershell
npm install -g clerk
clerk auth login
clerk init --app app_3KPkFbkBcI1Rfuk4dLRTMMfxQ1I
clerk env pull --app app_3KPkFbkBcI1Rfuk4dLRTMMfxQ1I --file ../backend/.env
clerk doctor
```

Complete the browser authorization opened by `clerk auth login` before running
initialization. A Clerk dashboard login alone does not complete CLI authorization.
The backend env pull keeps both servers connected to the same Clerk application.
Restart both servers after the keys have been written. The integration uses the
Clerk shadcn theme and includes `/__clerk/:path*` in the Next.js proxy matcher.

For manual configuration instead:

Create a Clerk application in the [Clerk dashboard](https://dashboard.clerk.com/).
Choose the sign-in methods you want. Use the **same application** for both servers.

Backend configuration, in `backend/.env` or project-root `.env`:

```dotenv
GEMINI_API_KEY=your_actual_gemini_key
TAVILY_API_KEY=your_actual_key
CLERK_SECRET_KEY=your_actual_clerk_secret_key
CLERK_AUTHORIZED_PARTIES=http://localhost:3000,http://127.0.0.1:3000

# Optional: Cloudflare R2 Persistent Storage (free tier: 10 GB storage, zero egress fees)
# If omitted or left blank, files are stored on local backend disk (ephemeral on free Render).
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY_ID=your_r2_access_key_id
R2_SECRET_ACCESS_KEY=your_r2_secret_access_key
R2_BUCKET_NAME=your_r2_bucket_name

# Optional: Ultra-low RAM embedding mode for Render 512 MB tier
# "local"  -> sentence-transformers/all-MiniLM-L6-v2 (~420 MB peak RAM)
# "gemini" -> Google text-embedding-004 via API (~150 MB peak RAM, zero PyTorch overhead)
EMBEDDING_PROVIDER=local

# Optional: Scanned PDF OCR (enabled by default; uses your existing GEMINI_API_KEY)
GEMINI_OCR_ENABLED=true
GEMINI_OCR_MODEL=gemini-2.5-flash
MAX_UPLOAD_MB=10
```

`core/config.py` reads root `.env` first and `backend/.env` second. Nonempty
backend values override root values; process environment overrides both.
Empty template values do not hide a root key. Never commit either file.

Frontend configuration:

```powershell
cd C:\Users\91991\Desktop\crag\aether-research\frontend
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
notepad .env.local
```

```dotenv
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_actual_clerk_publishable_key
CLERK_SECRET_KEY=your_actual_clerk_secret_key
BACKEND_API_URL=http://127.0.0.1:8000/api
```

Only the publishable key is public. `CLERK_SECRET_KEY` is used by the Next.js
**server**, never the browser. Gemini and Tavily keys remain exclusively on
the Python backend. The browser talks to `/api/backend`; the Next.js server adds
a Clerk bearer token and forwards real SSE and authorized file downloads.

Optionally configure `CLERK_JWT_KEY` on the backend with Clerk's PEM public key
for networkless signature verification. Otherwise the official SDK fetches and
caches the application's signing keys. Use quoted multiline dotenv syntax for PEM.
Keep allowed origins aligned with your frontend address.

If Clerk is not configured, landing and setup screens work but private access
stays closed. There is no development authentication bypass in the application.

### 2. Start both programs

Terminal one:

```powershell
cd C:\Users\91991\Desktop\crag\aether-research\backend
uv sync --frozen
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal two:

```powershell
cd C:\Users\91991\Desktop\crag\aether-research\frontend
npm ci
npm run dev
```

Open [Crebry](http://localhost:3000), enter the research workspace, sign up/sign in,
and create your first workspace. Upload `examples/research-notes.md`, select a
free model, and ask “What chunk size and overlap does Crebry use, and why?”

Restart after environment changes. For a production frontend preview, run
`npm run build` and then `npm run start`; rebuild after changing public Clerk keys.
Stop each server with Ctrl+C. Use one backend worker for the current locks and
embedded Chroma implementation.

## Existing data from the single-user version

Startup adds a nullable `owner_id` column without deleting old records. Old
workspaces are deliberately **unassigned** and hidden from all signed-in users.
No account automatically receives someone else's old data.

After the updated backend has started once, stop it. Find your own `user_...` ID
in the Clerk dashboard. From backend, explicitly claim your old data:

```powershell
.\.venv\Scripts\python.exe -m scripts.claim_legacy user_YOUR_ACTUAL_ID --all
```

Or use `--workspace WORKSPACE_ID` instead of `--all`. The script backs up SQLite
first and updates only previously unowned workspaces. It never changes an existing
owner. Restart the backend. Do not run this command with another person's user ID.

## Gemini free tier, availability, and latency

Create a key in [Google AI Studio](https://aistudio.google.com/apikey), add
`GEMINI_API_KEY` to backend/.env, and restart FastAPI. `GOOGLE_API_KEY` is also
accepted; `GEMINI_API_KEY` takes precedence. Old OpenRouter keys are ignored.
Do not put the Gemini key in frontend configuration or commit it.

**Use a free-tier Google project with billing disabled to avoid charges.** There
is no special free model suffix or API request flag that guarantees free billing.
The same eligible model can incur charges when used by a billing-enabled project.
Google may use free-tier content to improve its products; check its current terms.

`services/free_models.py` reads the official Gemini pricing page and Google's
authenticated, paginated Models API. It includes accessible Gemini models that
support text generation and have free Standard input/output prices. Image, audio,
live, speech, embeddings, robotics, paid-only, and unknown-price models are excluded.
The intersection is cached for five minutes. Refresh in the composer reloads both
sources. If pricing or access cannot be verified, chat fails closed.

The chosen model is first. Other candidates prefer newer model families, then Pro,
Flash, and Lite within a family, then stable versions. This is an explicit quality
heuristic, not a measured benchmark. A candidate gets at most one extra attempt
per operation for a transient transport/server failure.
A stale Gemini choice is visibly replaced by a currently verified candidate.

The API does not report remaining quota. Real 429 errors trigger fallback and a
60-second cooldown; 404 model-access failures use a five-minute cooldown. The
selector counts down and re-enables models automatically when cooldowns expire.
Transport and temporary server failures can get one retry per candidate; timeouts
switch directly to another candidate when possible. Each operation allows at most
three model attempts within 75 seconds by default. These limits are configurable
with `GEMINI_MAX_MODEL_ATTEMPTS` and `GEMINI_OPERATION_TIMEOUT_SECONDS`. Failures do not
disable models for unrelated requests or later workflow steps. Empty and truncated
answers trigger fallback without marking the model globally unavailable. Cooldowns
are scoped to the backend's current key. Invalid keys and invalid requests do not
trigger model hopping. A partial failed answer is reset before a replacement
streams. If candidates are exhausted, the UI and sanitized backend logs retain the
last failure's category and HTTP status rather than reporting a generic quota error.
Changing models cannot bypass shared project quotas, daily limits, or account restrictions.

A model appearing in Models.list and having published free pricing does not prove
that generation is enabled for the current project. Google currently limits Gemini
2.5 access to projects that previously used those models; new projects should use
current Gemini 3 models. See [Google's model access notes](https://ai.google.dev/gemini-api/docs/deprecations).

All grading, sufficiency checks, rewriting, generation, and grounding validation use
`ChatGoogleGenerativeAI` through Google's Gemini Developer API (`vertexai=False`).
Provider retries are disabled. Requests use a 30-second transport timeout, an
8,192-token output cap, and low thinking for Gemini 3; Gemini 2.5 Flash thinking is
disabled. Thought/signature blocks are not streamed into the visible answer.
Tavily web search and local MiniLM embeddings remain separate.

Grading sends all retrieved chunk IDs and texts in one request, validates complete,
unique ID coverage, and emits each chunk's separate score and reason. Structured
judgments use a 2,048-token output cap, configurable with
`GEMINI_STRUCTURED_MAX_OUTPUT_TOKENS`; answer generation retains its 8,192-token cap.
Exhausted provider failures during grading, sufficiency assessment, or grounding
validation stop the run with the service error. They do not trigger web search or
answer regeneration by treating an outage as a negative evidence judgment.
Citation correction
can regenerate once, and evidence/grounding checks remain intact. No fixed latency
is promised: quotas, model queues, network, and initial embedding load still matter.

## Tests

From backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.test-tmp-my-run
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.smoke_local
```

Pytest owns the selected temporary directory. Never point `--basetemp` at your
application data. Tests use real SQLite/Chroma with a test-only embedder and mock
external APIs. Auth tests also exercise the actual Clerk SDK with generated RSA
keys, testing signatures, expiry and allowed origins without a hosted account.

The authenticated `scripts.smoke_api` requires a current Clerk session token in
the process environment `AETHER_SMOKE_SESSION_TOKEN`. It creates and cleans up
only its temporary workspace. Never commit or log a session token. Beginners can
instead verify upload, preview, reindex, and deletion through the signed-in UI.

From frontend: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
See VERIFICATION.md for actual results. A production build does not prove your
Clerk account configuration or free-model availability.

## API and security boundary

`GET /api/health` is public. All other API endpoints require a Clerk session:
workspace CRUD; document list/upload/preview/download/reindex/delete; conversation
list/read/delete; chat SSE; free models; workspace-owned workflow trace list/read.
`/api/settings` was removed. `/docs` describes the API schemas; it does not grant
data access. Requests with guessed workspace or child IDs cannot bypass ownership.

SQLite/Chroma/files reside in `backend/data`. Source instructions are untrusted;
the graph cannot execute them. Raw Markdown HTML and generated image tags are
disabled. Citation checks verify IDs; grounding checks can still miss mistakes.
Tavily supplies snippets, not independently crawled full pages.

Authentication is implemented, but this remains a single-process reference app.
No public deployment was performed. Before exposing it widely, add per-user
storage/request quotas, rate limits, monitored backups, TLS, spending controls,
and infrastructure suitable for concurrent users. There is no OCR, durable job
queue, resumable provider stream, or distributed transaction between SQLite and
Chroma. Existing cited excerpts remain in saved messages after document deletion.
Deleting a Clerk account does not automatically delete its stored research data;
delete its workspaces first or implement an account-deletion webhook policy.

## Official references

- [Clerk Python authentication](https://clerk.com/articles/how-to-add-authentication-to-a-python-backend-2)
- [Clerk Next.js middleware](https://clerk.com/docs/reference/nextjs/clerk-middleware)
- [Gemini pricing and free tier](https://ai.google.dev/gemini-api/docs/pricing)
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
