from app.core.config import Config


def test_gemini_key_precedes_google_key_and_google_alias_is_supported(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key")
    assert Config(_env_file=None).gemini_api_key == "gemini-test-key"
    monkeypatch.delenv("GEMINI_API_KEY")
    assert Config(_env_file=None).gemini_api_key == "google-test-key"


def test_root_keys_survive_empty_backend_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text("GEMINI_API_KEY=root-test-key\nTAVILY_API_KEY=root-search-key\n")
    backend_env.write_text("GEMINI_API_KEY=\nTAVILY_API_KEY=\n")
    settings = Config(_env_file=(root_env, backend_env))
    assert settings.gemini_api_key == "root-test-key"
    assert settings.tavily_api_key == "root-search-key"


def test_backend_values_and_environment_take_priority(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text("GEMINI_API_KEY=root-test-key\n")
    backend_env.write_text("GEMINI_API_KEY=backend-test-key\n")
    assert Config(_env_file=(root_env, backend_env)).gemini_api_key == "backend-test-key"
    monkeypatch.setenv("GEMINI_API_KEY", "environment-test-key")
    assert Config(_env_file=(root_env, backend_env)).gemini_api_key == "environment-test-key"
