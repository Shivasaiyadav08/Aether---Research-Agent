"""Fail closed on production configuration that can lose data or incur API charges."""
from app.core.config import config
from urllib.parse import urlsplit


def check_production_configuration():
    postgres = config.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))
    if config.vector_provider == "supabase":
        if not postgres:
            raise RuntimeError("VECTOR_PROVIDER=supabase requires a PostgreSQL DATABASE_URL from the Supabase session pooler.")
        if config.embedding_provider != "gemini" or not config.gemini_api_key:
            raise RuntimeError("Supabase vector search requires EMBEDDING_PROVIDER=gemini and GEMINI_API_KEY (768 dimensions).")
    supabase_files = config.storage_provider == "supabase"
    if supabase_files:
        endpoint = urlsplit(config.supabase_url)
        if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password
                or endpoint.path not in {"", "/"} or endpoint.query or endpoint.fragment
                or not config.supabase_secret_key or not config.supabase_storage_bucket):
            raise RuntimeError("Supabase storage requires HTTPS SUPABASE_URL, a backend SUPABASE_SECRET_KEY and a private SUPABASE_STORAGE_BUCKET.")
        if config.supabase_secret_key.startswith("sb_publishable_"):
            raise RuntimeError("Use a backend Supabase secret key, not a publishable key.")
    if config.environment != "production":
        return
    if not config.clerk_issuer or not config.clerk_issuer.startswith("https://"):
        raise RuntimeError("Production requires CLERK_ISSUER from the same Clerk application as the frontend.")
    if not (config.clerk_secret_key or config.clerk_jwt_key):
        raise RuntimeError("Production requires Clerk verification credentials.")
    if not config.gemini_api_key or not config.gemini_free_project_confirmed or config.gemini_project_id == "local":
        raise RuntimeError("Production requires a Gemini project ID and confirmation that billing is disabled. Free pricing alone cannot prevent charges on a billed project.")
    if not config.frontend_origin.startswith("https://") or config.frontend_origin not in [part.strip() for part in config.clerk_authorized_parties.split(",")]:
        raise RuntimeError("Configure the production HTTPS frontend origin and CLERK_AUTHORIZED_PARTIES.")
    remote_vectors = config.vector_provider == "supabase" or bool(config.chroma_host)
    r2_files = (config.storage_provider in {"auto", "r2"} and config.r2_account_id and config.r2_bucket_name
                and config.r2_access_key_id and config.r2_secret_access_key)
    external = bool(postgres and remote_vectors and (supabase_files or r2_files))
    if not external:
        root = config.persistent_data_root
        if root is None or not root.is_mount() or not config.data_dir.resolve().is_relative_to(root.resolve()):
            raise RuntimeError("Production metadata, vectors and uploads require Supabase PostgreSQL/vector/storage, external PostgreSQL/Chroma/R2, or a mounted persistent DATA_DIR. Refusing ephemeral storage.")
        if config.database_url.startswith("sqlite:"):
            from pathlib import Path
            from sqlalchemy.engine import make_url
            database = make_url(config.database_url).database
            if not database or database == ":memory:" or not Path(database).resolve().is_relative_to(root.resolve()):
                raise RuntimeError("Production SQLite DATABASE_URL must also be inside the persistent mount.")
