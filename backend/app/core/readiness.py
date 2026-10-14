"""Fail closed on production configuration that can lose data or incur API charges."""
from app.core.config import config


def check_production_configuration():
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
    external = bool(config.database_url and not config.database_url.startswith("sqlite:")
                    and config.chroma_host and config.r2_account_id and config.r2_bucket_name
                    and config.r2_access_key_id and config.r2_secret_access_key)
    if not external:
        root = config.persistent_data_root
        if root is None or not root.is_mount() or not config.data_dir.resolve().is_relative_to(root.resolve()):
            raise RuntimeError("Production metadata, vectors and uploads require a mounted persistent DATA_DIR or external database, Chroma and R2. Refusing ephemeral storage.")
        if config.database_url.startswith("sqlite:"):
            from pathlib import Path
            from sqlalchemy.engine import make_url
            database = make_url(config.database_url).database
            if not database or database == ":memory:" or not Path(database).resolve().is_relative_to(root.resolve()):
                raise RuntimeError("Production SQLite DATABASE_URL must also be inside the persistent mount.")
