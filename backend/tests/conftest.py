import hashlib
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient
from fastapi import Request

from app.core.config import config
from app.core.auth import verify_session
from app.main import app
from app.services.vector import VectorStore


class TestEmbedder:
    """Deterministic offline vectors for storage tests, never used by the application."""

    def encode(self, texts, **_):
        vectors = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"\w+", text.lower()):
                slot = int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 64
                vectors[row, slot] += 1
            norm = np.linalg.norm(vectors[row])
            vectors[row] /= norm or 1
        return vectors


@pytest.fixture
def vectors(tmp_path):
    return VectorStore(tmp_path, "test-only", TestEmbedder())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", tmp_path)
    monkeypatch.setattr(config, "gemini_api_key", "")
    monkeypatch.setattr(config, "tavily_api_key", "")
    monkeypatch.setattr(config, "gemini_free_rpm", 1000)
    monkeypatch.setattr(config, "gemini_free_rpd", 10000)
    monkeypatch.setattr(
        "app.main.VectorStore", lambda directory, model: VectorStore(directory, model, TestEmbedder())
    )

    def offline_user(request: Request):
        return None if request.url.path == "/api/health" else request.headers.get("X-Test-User", "user_alice")

    async def offline_models():
        return [
            {
                "id": "gemini-test-flash",
                "name": "Test free model",
                "pricing": {"prompt": "0", "completion": "0"},
                "free_tier_eligible": True,
                "context_length": 1000000,
                "output_token_limit": 65536,
                "supported_parameters": ["structured_outputs", "streaming"],
            }
        ]

    monkeypatch.setattr("app.api.routes.get_free_models", offline_models)
    app.dependency_overrides[verify_session] = offline_user
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def workspace(client):
    return client.post("/api/workspaces", json={"name": "My Research"}).json()["id"]
