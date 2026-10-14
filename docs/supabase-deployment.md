# Render Free + Supabase Free

Crebry keeps Clerk authentication and its existing SQLAlchemy/LangGraph jobs. Supabase
stores metadata, conversations, routing state and job checkpoints in PostgreSQL,
768-dimensional Gemini embeddings in pgvector, and original documents in private
Storage. Render's local directory is only scratch space. Vercel configuration stays unchanged.

## Configure Supabase

1. Create/select a Supabase **Free** project. Keep the database password private.
2. Open **SQL Editor**, paste `backend/supabase/setup.sql`, and run it. It creates
   the private `crebry` schema, pgvector table and private `crebry-documents` bucket.
   It does not drop tables, delete rows or alter an existing bucket's visibility.
3. Keep `crebry` **out of the Data API exposed schemas**. No browser table grants
   or Storage access policies are needed: the backend authenticates Clerk users
   and enforces workspace ownership before accessing documents or vectors.
4. Click **Connect -> Session pooler**, and copy its PostgreSQL connection string.
   Replace `[YOUR-PASSWORD]` with the database password, URL-encoding reserved
   characters (`@` becomes `%40`, for example). Use the supplied host and username,
   usually port **5432**, not the transaction pooler's 6543. `DIRECT_URL` is a
   Prisma convention and is not required by this SQLAlchemy backend.
5. Copy the project URL and a **backend secret API key** (`sb_secret_...`) from
   **Settings -> API Keys**. A legacy `service_role` key is also accepted. Do not
   use a publishable/anon key, and never place secrets in Vercel public variables.

## Configure Render

Keep Docker, root directory `backend`, Dockerfile `Dockerfile`, build context `.`,
Docker Command empty and health check `/api/health`. Keep the Free instance.

Set these under **Render -> Environment**, using your real values:

```dotenv
ENVIRONMENT=production
DATABASE_URL=postgresql://YOUR_POOLER_USER:YOUR_ENCODED_PASSWORD@YOUR_POOLER_HOST:5432/postgres?sslmode=require
VECTOR_PROVIDER=supabase
STORAGE_PROVIDER=supabase
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SECRET_KEY=YOUR_BACKEND_SECRET_API_KEY
SUPABASE_STORAGE_BUCKET=crebry-documents
DATA_DIR=/var/data/crebry
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=YOUR_EXISTING_GEMINI_KEY
GEMINI_PROJECT_ID=YOUR_GOOGLE_PROJECT_ID
GEMINI_FREE_PROJECT_CONFIRMED=true
CLERK_SECRET_KEY=YOUR_EXISTING_CLERK_SECRET_KEY
CLERK_ISSUER=https://YOUR_EXISTING_CLERK_FRONTEND_API_DOMAIN
FRONTEND_ORIGIN=https://crebry-research-agent.vercel.app
CLERK_AUTHORIZED_PARTIES=https://crebry-research-agent.vercel.app
```

Only confirm the Google free project after verifying billing is disabled. Keep
the same Clerk application/instance as Vercel. Optional `TAVILY_API_KEY` enables
web search; document research works without it. No `PERSISTENT_DATA_ROOT`, R2,
Chroma host, Supabase Auth, or frontend Supabase variables are needed for this mode.
Supabase credentials override no existing local data; a new project starts empty.

Save and deploy the commit containing these adapters. On startup the backend
creates missing metadata tables in `crebry`, enables RLS without browser policies
and revokes browser grants, verifies the vector table and private
bucket, and refuses to silently use a local database or file fallback in this mode.
It uses TLS, a small connection pool, and disables prepared statements. Embedding
generation is lazy; Chroma is not initialized in Supabase mode.

Static configuration checks run before heavy imports and report all detected
mistakes together without printing secrets. A malformed or unencoded database
password, PostgreSQL URL used as a Storage key, anon/publishable key, quoted
bucket name, mismatched projects and wrong pooler mode receive specific errors.
In Supabase mode, an unwritable `DATA_DIR` falls back to a private temporary
scratch directory; PostgreSQL, vectors and originals remain in Supabase.

The effective upload limit is the smaller of `MAX_UPLOAD_MB` and the bucket's
byte limit. A smaller bucket limit is a warning, not a startup failure. The API
enforces it and `/api/health` exposes the effective limit for the frontend. You
do not need to increase Storage limits just to get the backend running. A
missing bucket, invalid credentials or a public bucket still fails safely.

## Verify and preserve existing data

- Check `/api/health`: `status=ok`, `vector_provider=supabase`,
  `storage_provider=supabase` and `embedding_provider=gemini`.
- Sign in, create a workspace, upload a small text/PDF document, ask a grounded
  question, download the original and verify its citations. Sign into the same
  Clerk account on another device and check the saved conversation.
- Redeploy and confirm the workspace, document and conversation remain available.
- Existing SQLite/Chroma/uploads have **not been migrated or deleted**. Back up
  those files before any migration. An empty new Supabase project will not show
  the old data until it is explicitly copied with original Clerk owner IDs.
  Do not reassign existing owned workspaces or drop the previous data.
- For rollback, restore the previous provider environment and commit against the
  original durable storage. Keep Supabase intact; changing providers is not a
  migration and must not silently discard the newly stored data.

For local SQLite/Chroma development, use `ENVIRONMENT=development`,
`VECTOR_PROVIDER=chroma`, `STORAGE_PROVIDER=auto`, unset `DATABASE_URL`, and choose
a writable local `DATA_DIR` (e.g. `data`). Existing local storage remains supported.
The Docker Compose file is for local use; Render does not run Compose.

## Limits and verification

Supabase Free currently includes 500 MB database and 1 GB Storage; embeddings and
job events count toward database space. It can pause after a week of inactivity
and does not include automatic backups. Render Free still sleeps on inactivity.
Exact cosine search preserves recall for small datasets; it does not yet have an
approximate vector index. No claim of unlimited capacity or production SLA is made.

102 focused local tests passed after the deployment fixes, covering configuration,
mocked private Storage REST/auth/errors and vector operations, and existing API
ownership/document/research-job behavior. Smaller bucket limits, malformed URLs,
secret-key confusion, combined diagnostics and scratch fallback have regressions.
Ruff and whitespace checks passed. Hosted Supabase
connectivity and an actual redeploy require the project credentials configured by
the operator; no live migration or deployment was executed by this task.

References: [Supabase pricing](https://supabase.com/pricing),
[connection strings](https://supabase.com/docs/guides/database/connecting-to-postgres),
[API keys](https://supabase.com/docs/guides/getting-started/api-keys),
[vector columns](https://supabase.com/docs/guides/ai/vector-columns).
