import sqlite3
from time import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from app.core.auth import verify_session
from app.main import app
from app.core.config import config
from app.models.database import create_database


def test_protected_api_rejects_unsigned_requests(client):
    override = app.dependency_overrides.pop(verify_session)
    try:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/workspaces").status_code == 401
        assert client.get("/api/models").status_code == 401
        assert client.post("/api/workspaces", json={"name": "Unsigned"}).status_code == 401
    finally:
        app.dependency_overrides[verify_session] = override


def test_other_user_cannot_access_any_workspace_resource(client, workspace, monkeypatch):
    from test_api import upload

    document = upload(client, workspace).json()[0]["document"]
    root = f"/api/workspaces/{workspace}"
    stranger = {"X-Test-User": "user_bob"}
    assert client.get("/api/workspaces", headers=stranger).json() == []
    for path in (
        "/documents",
        f"/documents/{document['id']}",
        f"/documents/{document['id']}/file",
        "/conversations",
        "/workflows",
        "/conversations/unknown",
        "/workflows/unknown",
    ):
        assert client.get(root + path, headers=stranger).status_code == 404
    assert client.patch(root, json={"name": "Stolen"}, headers=stranger).status_code == 404
    assert (
        client.post(root + "/documents", files=[("files", ("fake.txt", b"x"))], headers=stranger).status_code
        == 404
    )
    assert client.post(root + f"/documents/{document['id']}/reindex", headers=stranger).status_code == 404
    for path in ("", f"/documents/{document['id']}", "/conversations/unknown"):
        assert client.delete(root + path, headers=stranger).status_code == 404
    monkeypatch.setattr(config, "gemini_api_key", "test-only")
    assert (
        client.post(
            "/api/chat/stream",
            json={"workspace_id": workspace, "question": "Read private evidence"},
            headers=stranger,
        ).status_code
        == 404
    )
    assert len(client.get(root + "/documents").json()) == 1
    created = client.post(
        "/api/workspaces", json={"name": "Bob's project", "owner_id": "user_alice"}, headers=stranger
    ).json()
    assert created["owner_id"] == "user_bob"
    assert created["id"] not in {row["id"] for row in client.get("/api/workspaces").json()}


def test_legacy_workspace_migration_preserves_but_does_not_claim(tmp_path):
    with sqlite3.connect(tmp_path / "aether.db") as db:
        db.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, created_at TEXT)")
        db.execute("INSERT INTO workspaces VALUES ('legacy', 'Private old data', '2026-10-08')")
    engine, _ = create_database(tmp_path)
    with engine.connect() as connection:
        row = connection.exec_driver_sql("SELECT name,owner_id FROM workspaces WHERE id='legacy'").one()
        assert row == ("Private old data", None)
    engine.dispose()


def test_legacy_claim_backs_up_and_never_reassigns_existing_owner(tmp_path, monkeypatch):
    from app.models.database import Workspace
    from scripts.claim_legacy import main

    engine, factory = create_database(tmp_path)
    with factory() as db:
        db.add_all(
            [
                Workspace(id="old", name="Unassigned", owner_id=None),
                Workspace(id="owned", name="Bob's data", owner_id="user_bob"),
            ]
        )
        db.commit()
    monkeypatch.setattr(config, "data_dir", tmp_path)
    monkeypatch.setattr("sys.argv", ["claim_legacy", "user_alice", "--all"])
    main()
    with factory() as db:
        assert db.get(Workspace, "old").owner_id == "user_alice"
        assert db.get(Workspace, "owned").owner_id == "user_bob"
    backups = list(tmp_path.glob("aether-before-claim-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT owner_id FROM workspaces WHERE id='old'").fetchone() == (None,)
    engine.dispose()


def request_with_token(token=None):
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/workspaces",
            "headers": headers,
            "scheme": "http",
            "server": ("localhost", 8000),
            "query_string": b"",
        }
    )


def test_real_clerk_sdk_checks_signature_expiry_and_origin(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    monkeypatch.setattr(config, "clerk_jwt_key", public_pem)
    monkeypatch.setattr(config, "clerk_secret_key", "")
    monkeypatch.setattr(config, "clerk_authorized_parties", "http://localhost:3000")
    claims = {
        "sub": "user_alice",
        "sid": "sess_test",
        "iss": "https://test.clerk.accounts.dev",
        "azp": "http://localhost:3000",
        "iat": int(time()),
        "nbf": int(time()) - 1,
        "exp": int(time()) + 120,
    }
    token = jwt.encode(claims, private, algorithm="RS256")
    assert verify_session(request_with_token(token)) == "user_alice"
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for bad in (
        None,
        "not-a-jwt",
        jwt.encode(claims, wrong_key, algorithm="RS256"),
        jwt.encode({**claims, "exp": int(time()) - 60}, private, algorithm="RS256"),
        jwt.encode({**claims, "azp": "https://attacker.example"}, private, algorithm="RS256"),
    ):
        with pytest.raises(HTTPException) as rejected:
            verify_session(request_with_token(bad))
        assert rejected.value.status_code == 401
