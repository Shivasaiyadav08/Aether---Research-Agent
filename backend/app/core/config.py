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
     """
    Central configuration manager for the backend.

    WHY THIS CLASS EXISTS:
    Instead of hardcoding API keys, model names, URLs, and limits throughout
    the application, we define them in one place.

    BaseSettings loads values from environment variables and configured .env files.
    Keeping secrets in backend configuration helps prevent exposing them to browsers.
    """
    
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
    clerk_authorized_parties: str = "http://localhost:3000,http://127.0.0.1:3000"
    gemini_model: str = "auto"
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    frontend_origin: str = "http://localhost:3000"
    max_upload_mb: int = Field(default=20, ge=1, le=100)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


config = Config()
