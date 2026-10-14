from pathlib import Path
# AliasChoices allows a setting to accept more than one environment variable name.
# Field lets us define defaults and validation rules for configuration values.
from pydantic import AliasChoices, Field
# BaseSettings automatically reads configuration from environment variables and .env files.
# SettingsConfigDict is used to configure how BaseSettings loads those values.

from pydantic_settings import BaseSettings, SettingsConfigDict
# PROJECT PATH SETUP
# __file__ refers to this Python file.
# resolve() converts its location into an absolute path.
# parents[2] moves two levels up from the file's parent directory.
# This gives us the path used as the backend/project directory in this application.
# We use pathlib.Path instead of manually joining strings to make path handling
# more reliable across operating systems.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    
    # Central configuration manager for the backend.

    # WHY THIS CLASS EXISTS:
    # Instead of hardcoding API keys, model names, URLs, and limits throughout
    # the application, we define them in one place.

    # BaseSettings loads values from environment variables and configured .env files.
    # Keeping secrets in backend configuration helps prevent exposing them to browsers.
    
    
    # CONFIGURATION LOADING RULES
    model_config = SettingsConfigDict(
        # Read configuration from two .env files:
        # 1. The .env file in BACKEND_DIR.parent (the parent of BACKEND_DIR).
        # 2. The .env file inside BACKEND_DIR.
        #
        # Environment variables supplied by the operating system can also be read.
        # If the same setting appears in multiple sources, the effective precedence
        # depends on Pydantic Settings' source priority; OS environment variables
        # normally take priority over .env values.
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        # Ignore empty environment variable values instead of using them
        # to overwrite configured defaults with empty strings.
        env_ignore_empty=True,

        # Ignore extra configuration keys found in .env files that do not
        # correspond to fields declared in this Config class.
        #
        # This is useful when a shared .env file contains settings for
        # multiple parts of a project.
        extra="ignore",
    )
    gemini_api_key: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"))
    tavily_api_key: str = ""
    clerk_secret_key: str = ""
    clerk_jwt_key: str = ""
    clerk_issuer: str = ""
    clerk_authorized_parties: str = "http://localhost:3000,http://127.0.0.1:3000"
    gemini_model: str = "auto"
    gemini_project_id: str = "local"
    gemini_retry_rounds: int = Field(default=1, ge=0, le=1)
    gemini_max_concurrency: int = Field(default=2, ge=1, le=8)
    gemini_free_rpm: int = Field(default=5, ge=1, le=1000)
    gemini_free_rpd: int = Field(default=20, ge=1, le=10000)
    gemini_free_tpm: int = Field(default=125000, ge=8192, le=2000000)
    research_timeout_seconds: float = Field(default=240, ge=30, le=600)
    max_research_jobs: int = Field(default=2, ge=1, le=8)
    user_requests_per_minute: int = Field(default=120, ge=10, le=1000)
    database_url: str = ""
    vector_provider: str = Field(default="chroma", pattern=r"^(chroma|supabase)$")
    storage_provider: str = Field(default="auto", pattern=r"^(auto|local|r2|supabase)$")
    supabase_url: str = ""
    supabase_secret_key: str = Field(default="", validation_alias=AliasChoices("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"))
    supabase_storage_bucket: str = "crebry-documents"
    environment: str = Field(default="development", pattern=r"^(development|test|production)$")
    persistent_data_root: Path | None = None
    gemini_free_project_confirmed: bool = False
    chroma_host: str = ""
    chroma_port: int = Field(default=8000, ge=1, le=65535)
    chroma_ssl: bool = True
    chroma_auth_token: str = ""
    gemini_max_model_attempts: int = Field(default=3, ge=1, le=8)
    gemini_operation_timeout_seconds: float = Field(default=75, ge=1, le=180)
    gemini_structured_max_output_tokens: int = Field(default=2048, ge=256, le=8192)
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    frontend_origin: str = "http://localhost:3000"
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = Field(default=32, ge=1, le=128)
    max_concurrent_embeddings: int = Field(default=1, ge=1, le=8)
    max_extracted_chars: int = Field(default=2_000_000, ge=10_000, le=10_000_000)
    enable_memory_diagnostics: bool = Field(default=True)
    gc_threshold_mb: float = Field(default=400.0, ge=100.0, le=2000.0)
    # Cloudflare R2 storage (optional — falls back to local disk when blank)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    # Embedding provider: "auto" (uses Gemini when GEMINI_API_KEY is set or on Render, else local),
    # or explicitly "gemini" (~110 MB RAM, recommended for Render 512 MB) or "local" (~420 MB RAM)
    embedding_provider: str = Field(default="auto", pattern=r"^(auto|local|gemini)$")
    # Gemini Cloud OCR for scanned PDFs (uses existing GEMINI_API_KEY)
    gemini_ocr_enabled: bool = Field(default=True)
    gemini_ocr_model: str = "gemini-3.1-flash-lite"


config = Config()
