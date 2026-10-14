import pytest

from app.core.config import config
from app.core.readiness import check_production_configuration


def production(monkeypatch):
    for field, value in {
        "environment": "production", "clerk_issuer": "https://example.clerk.accounts.dev",
        "clerk_secret_key": "test-only", "gemini_api_key": "test-only", "gemini_project_id": "test-project",
        "gemini_free_project_confirmed": True, "frontend_origin": "https://research.example",
        "clerk_authorized_parties": "https://research.example", "persistent_data_root": None,
        "database_url": "", "chroma_host": "",
        "vector_provider": "chroma", "storage_provider": "auto",
    }.items():
        monkeypatch.setattr(config, field, value)


def test_ephemeral_storage_is_refused_before_database_creation(tmp_path, monkeypatch):
    production(monkeypatch)
    monkeypatch.setattr(config, "data_dir", tmp_path / "never-created")
    with pytest.raises(RuntimeError, match="ephemeral"):
        check_production_configuration()
    assert not config.data_dir.exists()


def test_no_automatic_paid_usage_without_project_confirmation(monkeypatch):
    production(monkeypatch)
    monkeypatch.setattr(config, "gemini_free_project_confirmed", False)
    with pytest.raises(RuntimeError, match="billing"):
        check_production_configuration()


def test_configured_external_storage_passes(monkeypatch):
    production(monkeypatch)
    for field, value in {
        "database_url": "postgresql+psycopg://test", "chroma_host": "chroma.internal",
        "r2_account_id": "test", "r2_bucket_name": "test", "r2_access_key_id": "test", "r2_secret_access_key": "test",
    }.items():
        monkeypatch.setattr(config, field, value)
    check_production_configuration()
