"""Verify a running local backend without cloud calls: python -m scripts.smoke_api."""

from uuid import uuid4
import os

import httpx


def main():
    token = os.environ.get("AETHER_SMOKE_SESSION_TOKEN", "")
    if not token:
        raise SystemExit(
            "Set AETHER_SMOKE_SESSION_TOKEN to a current Clerk session token. Never commit or print it."
        )
    with httpx.Client(
        base_url="http://127.0.0.1:8000/api", timeout=180, headers={"Authorization": f"Bearer {token}"}
    ) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json()["status"] == "ok"
        response = client.post("/workspaces", json={"name": f"API smoke test {uuid4().hex[:8]}"})
        response.raise_for_status()
        workspace_id = response.json()["id"]
        path = f"/workspaces/{workspace_id}/documents"
        content = b"Aether uses local MiniLM embeddings and persistent Chroma to retrieve document evidence."
        try:
            uploaded = client.post(path, files={"files": ("verification.txt", content, "text/plain")})
            uploaded.raise_for_status()
            document = uploaded.json()[0]["document"]
            assert document["status"] == "ready", document
            document_path = f"{path}/{document['id']}"
            duplicate = client.post(path, files={"files": ("same-bytes.txt", content, "text/plain")})
            assert duplicate.json()[0]["duplicate"]
            assert len(client.get(path).json()) == 1
            assert "MiniLM" in client.get(document_path).json()["text"]
            assert client.get(document_path + "/file").content == content
            rebuilt = client.post(document_path + "/reindex")
            rebuilt.raise_for_status()
            assert rebuilt.json()["chunk_count"] == document["chunk_count"]
            removed = client.delete(document_path)
            removed.raise_for_status()
            assert client.get(path).json() == []
            print(
                "PASS: live FastAPI health, workspace creation, real MiniLM upload, duplicate detection, preview, download, reindex, and deletion."
            )
        finally:
            # Only the workspace created above is removed, never existing research data.
            client.delete(f"/workspaces/{workspace_id}").raise_for_status()


if __name__ == "__main__":
    main()
