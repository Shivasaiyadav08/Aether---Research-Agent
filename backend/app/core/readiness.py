"""Report all static startup mistakes together, without printing credentials."""
import base64
import json
import logging
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.core.config import config


def _backend_key_valid(key):
    if key != key.strip() or any(char.isspace() or char in "\"'" for char in key):
        return False
    if key.startswith("sb_secret_"):
        return True
    # Check legacy key shape/role only; Supabase verifies authenticity over HTTPS.
    try:
        parts = key.split(".")
        if len(parts) != 3:
            return False
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return isinstance(payload, dict) and payload.get("role") == "service_role"
    except (ValueError, TypeError):
        return False


def check_production_configuration():
    errors = []
    postgres = config.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))
    database = None
    if config.vector_provider == "supabase":
        if not postgres:
            errors.append("VECTOR_PROVIDER=supabase requires a PostgreSQL DATABASE_URL from Supabase Connect -> Session pooler.")
        else:
            try:
                database = make_url(config.database_url)
                if not all((database.username, database.password, database.host, database.database)) or "@" in database.host:
                    raise ValueError
                if database.host.endswith("pooler.supabase.com") and database.port != 5432:
                    errors.append("DATABASE_URL must use Supabase Session pooler port 5432, not transaction mode port 6543.")
            except (ValueError, TypeError, ArgumentError):
                database = None
                errors.append("DATABASE_URL is malformed or incomplete. Copy the Session pooler URL and percent-encode special password characters (@ -> %40).")
        if config.embedding_provider != "gemini" or not config.gemini_api_key:
            errors.append("Supabase vectors require EMBEDDING_PROVIDER=gemini and GEMINI_API_KEY (768 dimensions).")
    supabase_files = config.storage_provider == "supabase"
    if supabase_files:
        try:
            endpoint = urlsplit(config.supabase_url)
            valid_endpoint = (endpoint.scheme == "https" and endpoint.hostname and not endpoint.username
                and not endpoint.password and endpoint.path in {"", "/"} and not endpoint.query and not endpoint.fragment)
            if valid_endpoint:
                valid_endpoint = (not any(char.isspace() or char in "\"'" for char in endpoint.hostname)
                                  and endpoint.port in {None, 443})
        except ValueError:
            endpoint, valid_endpoint = None, False
        if not valid_endpoint:
            errors.append("SUPABASE_URL must be the HTTPS project URL, not a PostgreSQL connection string or a URL with an API path.")
        if not _backend_key_valid(config.supabase_secret_key):
            errors.append("SUPABASE_SECRET_KEY must be a backend sb_secret_ key or legacy service_role JWT; not a database URL/password or publishable/anon key.")
        bucket = config.supabase_storage_bucket
        if not bucket or any(char.isspace() or char in "\"'/\\" for char in bucket):
            errors.append("SUPABASE_STORAGE_BUCKET must be the exact private bucket name without quotes, spaces or a URL.")
        if valid_endpoint and database and endpoint.hostname.endswith(".supabase.co"):
            project = endpoint.hostname.removesuffix(".supabase.co")
            database_project = (database.username.removeprefix("postgres.") if database.username.startswith("postgres.")
                                else database.host.removeprefix("db.").removesuffix(".supabase.co")
                                if database.host.startswith("db.") and database.host.endswith(".supabase.co") else None)
            if database_project and project != database_project:
                errors.append("DATABASE_URL and SUPABASE_URL belong to different Supabase projects. Copy both from the same project.")
    if config.environment == "production":
        if not config.clerk_issuer.startswith("https://"):
            errors.append("CLERK_ISSUER must be the HTTPS issuer of the same Clerk instance as Vercel.")
        if not (config.clerk_secret_key or config.clerk_jwt_key):
            errors.append("Production requires Clerk verification credentials (CLERK_SECRET_KEY or CLERK_JWT_KEY).")
        if not config.gemini_api_key or not config.gemini_free_project_confirmed or config.gemini_project_id == "local":
            errors.append("Production requires GEMINI_API_KEY, GEMINI_PROJECT_ID and GEMINI_FREE_PROJECT_CONFIRMED=true only after verifying billing is disabled.")
        if not config.frontend_origin.startswith("https://") or config.frontend_origin not in [part.strip() for part in config.clerk_authorized_parties.split(",")]:
            errors.append("Configure HTTPS FRONTEND_ORIGIN and matching CLERK_AUTHORIZED_PARTIES.")
        remote_vectors = config.vector_provider == "supabase" or bool(config.chroma_host)
        r2_files = (config.storage_provider in {"auto", "r2"} and config.r2_account_id and config.r2_bucket_name
                    and config.r2_access_key_id and config.r2_secret_access_key)
        if not (postgres and remote_vectors and (supabase_files or r2_files)):
            root = config.persistent_data_root
            if root is None or not root.is_mount() or not config.data_dir.resolve().is_relative_to(root.resolve()):
                errors.append("Production requires Supabase PostgreSQL/vector/storage, external PostgreSQL/Chroma/R2, or a persistent mount. Refusing ephemeral user data.")
            elif config.database_url.startswith("sqlite:"):
                filename = make_url(config.database_url).database
                if not filename or filename == ":memory:" or not Path(filename).resolve().is_relative_to(root.resolve()):
                    errors.append("Production SQLite DATABASE_URL must also be inside the persistent mount.")
    if errors:
        raise RuntimeError("Backend configuration needs correction:\n- " + "\n- ".join(errors))


def prepare_supabase_scratch_directory():
    """Only external-data mode may fall back to temporary upload processing space."""
    if config.vector_provider != "supabase" or config.storage_provider != "supabase":
        return
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=config.data_dir):
            pass
    except OSError:
        config.data_dir = Path(tempfile.mkdtemp(prefix="crebry-scratch-"))
        logging.getLogger("aether").warning("DATA_DIR is not writable; using a private temporary upload directory. Supabase user data is unaffected.")
