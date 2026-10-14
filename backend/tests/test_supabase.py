from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.config import config
from app.core.readiness import check_production_configuration
from app.models.database import Workspace
from app.models import database
from app.services import storage, supabase_storage
from app.services.postgres_vector import PostgresVectorStore, vector_literal


@pytest.fixture
def supabase_config(monkeypatch):
    fields = {
        "environment": "production", "vector_provider": "supabase", "storage_provider": "supabase",
        "database_url": "postgresql+psycopg://test:test@pooler.example:5432/postgres",
        "supabase_url": "https://project.supabase.co", "supabase_secret_key": "sb_secret_test_only",
        "supabase_storage_bucket": "crebry-documents", "embedding_provider": "gemini",
        "gemini_api_key": "test-only", "gemini_project_id": "test-project", "gemini_free_project_confirmed": True,
        "clerk_issuer": "https://example.clerk.accounts.dev", "clerk_secret_key": "test-only",
        "frontend_origin": "https://research.example", "clerk_authorized_parties": "https://research.example",
        "persistent_data_root": None,
    }
    for field, value in fields.items():
        monkeypatch.setattr(config, field, value)


def test_supabase_production_needs_no_render_disk(supabase_config):
    check_production_configuration()


@pytest.mark.parametrize("field,value,match", [
    ("database_url", "sqlite:///data/aether.db", "PostgreSQL"),
    ("embedding_provider", "local", "768"),
    ("supabase_secret_key", "", "SUPABASE_SECRET_KEY"),
    ("supabase_secret_key", "sb_publishable_test", "publishable"),
    ("supabase_url", "http://project.supabase.co", "HTTPS"),
])
def test_supabase_cannot_silently_fall_back_to_local(supabase_config, monkeypatch, field, value, match):
    monkeypatch.setattr(config, field, value)
    with pytest.raises(RuntimeError, match=match):
        check_production_configuration()


def mock_http(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(supabase_storage.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def test_private_upload_download_and_delete_use_new_secret_auth(supabase_config, monkeypatch, tmp_path):
    objects = {}
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["apikey"] == "sb_secret_test_only"
        assert "authorization" not in request.headers
        if request.method == "POST":
            assert request.headers["x-upsert"] == "false"
            objects[request.url.path] = request.content
            return httpx.Response(200, json={"Key": "saved"})
        if request.method == "GET":
            return httpx.Response(200, content=objects[request.url.path])
        return httpx.Response(200, json=[])

    mock_http(monkeypatch, handler)
    source = tmp_path / "original.txt"
    source.write_bytes(b"Supabase preserves originals")
    storage.upload_file("workspace_a", "doc_a", source)
    assert storage.download_file("workspace_a", "doc_a") == source.read_bytes()
    storage.delete_file("workspace_a", "doc_a")
    assert calls[-1].content == b'{"prefixes":["uploads/workspace_a/doc_a"]}'
    assert not storage.file_exists_locally("workspace_a", "doc_a")
    assert storage.provider() == "supabase"


def test_legacy_service_role_uses_bearer(supabase_config, monkeypatch):
    monkeypatch.setattr(config, "supabase_secret_key", "legacy-service-role-jwt")

    def handler(request):
        assert request.headers["authorization"] == "Bearer legacy-service-role-jwt"
        return httpx.Response(200, content=b"private original")

    mock_http(monkeypatch, handler)
    assert storage.download_file("ws", "doc") == b"private original"


@pytest.mark.parametrize("public", [True, None])
def test_public_or_invalid_bucket_rejected(supabase_config, monkeypatch, public):
    mock_http(monkeypatch, lambda _: httpx.Response(200, json={"public": public}))
    with pytest.raises(RuntimeError, match="private"):
        supabase_storage.check_bucket()


def test_quota_error_does_not_write_local_fallback_or_leak_body(supabase_config, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "data_dir", tmp_path)
    mock_http(monkeypatch, lambda _: httpx.Response(413, text="internal secret diagnostics"))
    with pytest.raises(RuntimeError, match="HTTP 413") as error:
        storage.upload_file("ws", "doc", b"data")
    assert "secret diagnostics" not in str(error.value)
    assert not (tmp_path / "uploads").exists()


def test_workspace_delete_is_scoped_and_detects_failed_deletion(supabase_config, monkeypatch):
    def handler(request):
        assert b"uploads/workspace_a" in request.content
        if request.method == "POST":
            return httpx.Response(200, json=[{"name": "doc_a", "id": "file_id"}])
        return httpx.Response(200, json=[])

    mock_http(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="Workspace metadata was retained"):
        storage.delete_workspace_files("workspace_a")


@pytest.mark.parametrize("values", [[1.0], [float("nan")] * 768, [0] * 768])
def test_invalid_embedding_rejected(values):
    with pytest.raises(ValueError):
        vector_literal(values)


def test_retrieval_returns_citation_metadata_and_scopes_published_versions(tmp_path):
    connection = MagicMock()
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    connection.execute.return_value.scalar.return_value = 1
    connection.execute.return_value.mappings.return_value.all.return_value = [{
        "document_id": "doc_a", "name": "paper.pdf", "page": 7, "version": "published",
        "chunk": 3, "content": "Evidence from page seven", "distance": 0.125,
    }]
    embedder = MagicMock()
    embedder.embed_query.return_value = [1.0] + [0.0] * 767
    store = PostgresVectorStore(engine, tmp_path, "gemini", embedder)
    result = store.retrieve("workspace_a", "question")
    assert result == [{"id": "D1", "kind": "document", "text": "Evidence from page seven",
                       "similarity": 0.875, "document_id": "doc_a", "name": "paper.pdf",
                       "page": 7, "version": "published", "chunk": 3}]
    statement, params = connection.execute.call_args.args
    assert params["workspace"] == "workspace_a"
    assert "d.index_version = c.version" in str(statement)
    assert "d.workspace_id = c.workspace_id" in str(statement)
    embedder.embed_query.assert_called_once_with("question")
    store.delete_document("workspace_a", "doc_a", "failed-stage")
    deleted_statement, deleted_params = engine.begin.return_value.__enter__.return_value.execute.call_args.args
    assert deleted_params == {"workspace": "workspace_a", "document": "doc_a", "version": "failed-stage"}
    assert "workspace_id = :workspace" in str(deleted_statement)


def test_private_schema_translation_keeps_orm_out_of_public():
    compiled = select(Workspace).compile(dialect=postgresql.dialect(), schema_translate_map={None: "crebry"},
                                         render_schema_translate=True)
    assert "FROM crebry.workspaces" in str(compiled)


def test_missing_bucket_gives_setup_instruction(supabase_config, monkeypatch):
    mock_http(monkeypatch, lambda _: httpx.Response(404, json={"error": "not_found"}))
    with pytest.raises(RuntimeError, match="setup.sql"):
        supabase_storage.check_bucket()


@pytest.mark.parametrize("details", [{"code": "NoSuchBucket"}, {"error": "Bucket not found", "statusCode": "404"}])
def test_legacy_http_400_missing_bucket_gives_setup_instruction(supabase_config, monkeypatch, details):
    mock_http(monkeypatch, lambda _: httpx.Response(400, json=details))
    with pytest.raises(RuntimeError, match="setup.sql"):
        supabase_storage.check_bucket()


@pytest.mark.parametrize("code,match", [("InvalidJWT", "backend credential"), ("AccessDenied", "backend key"),
                                       ("InvalidBucketName", "without quotes")])
def test_storage_error_hints_never_echo_provider_messages(supabase_config, monkeypatch, code, match):
    mock_http(monkeypatch, lambda _: httpx.Response(400, json={"code": code, "message": "credential=secret-value"}))
    with pytest.raises(RuntimeError, match=match) as error:
        supabase_storage.check_bucket()
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize("schema_exists", [True, False])
def test_postgres_startup_checks_private_schema_and_denies_browser_roles(tmp_path, monkeypatch, schema_exists):
    engine = MagicMock()
    engine.dialect = postgresql.dialect()
    connection = engine.begin.return_value.__enter__.return_value
    connection.exec_driver_sql.return_value.scalar.return_value = "crebry" if schema_exists else "public"
    create = MagicMock(return_value=engine)
    monkeypatch.setattr(database, "create_engine", create)
    metadata_create = MagicMock()
    monkeypatch.setattr(database.Base.metadata, "create_all", metadata_create)
    listeners = []

    def listen(*_):
        def decorate(function):
            listeners.append(function)
            return function
        return decorate

    monkeypatch.setattr(database.event, "listens_for", listen)
    if not schema_exists:
        with pytest.raises(RuntimeError, match="setup.sql"):
            database.create_database(tmp_path, "postgresql://test", schema="crebry")
        metadata_create.assert_not_called()
        return
    database.create_database(tmp_path, "postgresql://test", schema="crebry")
    options = create.call_args.kwargs
    assert options["execution_options"]["schema_translate_map"] == {None: "crebry"}
    assert options["connect_args"]["sslmode"] == "require"
    assert options["connect_args"]["prepare_threshold"] is None
    assert options["pool_size"] + options["max_overflow"] == 5
    statements = [call.args[0] for call in connection.exec_driver_sql.call_args_list]
    assert any('ALTER TABLE "crebry"."workspaces" ENABLE ROW LEVEL SECURITY' in sql for sql in statements)
    assert any('REVOKE ALL ON TABLE "crebry"."documents" FROM PUBLIC, anon, authenticated' in sql for sql in statements)
    dbapi_connection = MagicMock()
    listeners[0](dbapi_connection, None)
    dbapi_connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
        "SET search_path TO crebry, extensions, public")
    dbapi_connection.commit.assert_called_once()
