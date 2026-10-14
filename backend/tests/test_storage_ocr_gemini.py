import numpy as np
import pymupdf
import pytest

from app.core.config import config
from app.services import storage
from app.services.documents import extract_text
from app.services.vector import VectorStore


@pytest.fixture(autouse=True)
def offline_ocr_catalog(monkeypatch):
    def catalog():
        return [{"id": model, "name": model, "available": True, "free_tier_eligible": True,
                 "context_length": 1000000, "output_token_limit": 65536,
                 "supported_parameters": ["vision", "streaming", "structured_outputs"]}
                for model in dict.fromkeys([config.gemini_ocr_model, "gemini-3.1-flash-lite", "gemini-3.8-flash"])]
    monkeypatch.setattr("app.services.free_models.get_free_models_sync", catalog)


def test_storage_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", tmp_path)
    monkeypatch.setattr(config, "r2_account_id", "")
    monkeypatch.setattr(config, "r2_bucket_name", "")

    ws_id = "ws_test_local"
    doc_id = "doc_123"
    test_bytes = b"Hello Local Storage"

    # Upload from bytes
    storage.upload_file(ws_id, doc_id, test_bytes)
    assert storage.file_exists_locally(ws_id, doc_id)
    assert storage.download_file(ws_id, doc_id) == test_bytes

    # Upload from path
    src_file = tmp_path / "source.txt"
    src_file.write_bytes(b"From file path")
    doc_id_path = "doc_path"
    storage.upload_file(ws_id, doc_id_path, src_file)
    assert storage.download_file(ws_id, doc_id_path) == b"From file path"

    # Delete single file
    storage.delete_file(ws_id, doc_id)
    assert not storage.file_exists_locally(ws_id, doc_id)

    # Delete workspace files
    storage.delete_workspace_files(ws_id)
    assert not (tmp_path / "uploads" / ws_id).exists()


def test_storage_r2_sigv4_signing(monkeypatch):
    monkeypatch.setattr(config, "r2_account_id", "test_account")
    monkeypatch.setattr(config, "r2_access_key_id", "test_access")
    monkeypatch.setattr(config, "r2_secret_access_key", "test_secret")
    monkeypatch.setattr(config, "r2_bucket_name", "my-bucket")

    headers = storage._sigv4_headers(
        method="PUT",
        bucket="my-bucket",
        key="uploads/ws/doc",
        region="auto",
        access_key="test_access",
        secret_key="test_secret",
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        host="test_account.r2.cloudflarestorage.com",
    )

    assert "Authorization" in headers
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=test_access/")
    assert "x-amz-date" in headers
    assert "x-amz-content-sha256" in headers
    assert headers["x-amz-content-sha256"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_storage_r2_mock_upload_download(monkeypatch):
    monkeypatch.setattr(config, "r2_account_id", "acc123")
    monkeypatch.setattr(config, "r2_access_key_id", "key123")
    monkeypatch.setattr(config, "r2_secret_access_key", "secret123")
    monkeypatch.setattr(config, "r2_bucket_name", "bucket123")

    uploaded = {}

    class MockResponse:
        def __init__(self, status_code, content=b""):
            self.status_code = status_code
            self.content = content
            self.text = content.decode("utf-8", errors="ignore")

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP error {self.status_code}")

    class MockClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def put(self, url, headers=None, content=None):
            uploaded[url] = content
            return MockResponse(200)

        def get(self, url, headers=None):
            if url in uploaded:
                return MockResponse(200, uploaded[url])
            return MockResponse(404)

        def delete(self, url, headers=None):
            uploaded.pop(url, None)
            return MockResponse(204)

    monkeypatch.setattr("httpx.Client", MockClient)

    storage.upload_file("ws1", "doc1", b"Cloud data")
    assert len(uploaded) == 1
    assert any("bucket123/uploads/ws1/doc1" in k for k in uploaded)

    data = storage.download_file("ws1", "doc1")
    assert data == b"Cloud data"

    storage.delete_file("ws1", "doc1")
    assert len(uploaded) == 0


def test_gemini_embedding_provider_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", tmp_path)
    monkeypatch.setattr(config, "embedding_provider", "gemini")
    monkeypatch.setattr(config, "gemini_api_key", "fake-key")

    import app.services.vector as vector_module
    vector_module._SHARED_EMBEDDER = None

    class MockGeminiEmbedder:
        def embed_documents(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(
        "langchain_google_genai.GoogleGenerativeAIEmbeddings",
        lambda **kwargs: MockGeminiEmbedder(),
    )

    store = VectorStore(data_dir=tmp_path, model_name="test-model")
    assert store._get_model() is not None

    embeddings = store.embed(["text one", "text two"])
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (2, 3)


def test_gemini_ocr_for_scanned_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "gemini_ocr_enabled", True)
    monkeypatch.setattr(config, "gemini_api_key", "fake-key")

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(pymupdf.Rect(50, 50, 200, 200), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    pdf_path = tmp_path / "scanned_sample.pdf"
    doc.save(str(pdf_path))
    doc.close()

    class MockOCRResponse:
        content = "Invoice 98765 Total Due: 150.00 USD"

    class MockLLM:
        def invoke(self, messages):
            return MockOCRResponse()

    monkeypatch.setattr("app.services.ai.create_llm", lambda model: MockLLM())

    segments = extract_text(pdf_path, ".pdf")
    assert len(segments) == 1
    assert segments[0]["page"] == 1
    assert "Invoice 98765 Total Due: 150.00 USD" in segments[0]["text"]


def test_gemini_ocr_list_content_blocks(tmp_path, monkeypatch):
    """Gemini vision models sometimes return content as a list of dicts.
    Ensure ocr_page_image() extracts plain text from content blocks correctly."""
    monkeypatch.setattr(config, "gemini_ocr_enabled", True)
    monkeypatch.setattr(config, "gemini_api_key", "fake-key")

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(pymupdf.Rect(10, 10, 290, 290), color=(0, 0, 0), fill=(1, 1, 1))
    pdf_path = tmp_path / "scanned_blocks.pdf"
    doc.save(str(pdf_path))
    doc.close()

    class MockListContentResponse:
        content = [
            {"type": "text", "text": "Hello scanned world", "extras": {"signature": "abc"}},
        ]

    class MockLLM:
        def invoke(self, messages):
            return MockListContentResponse()

    monkeypatch.setattr("app.services.ai.create_llm", lambda model: MockLLM())

    segments = extract_text(pdf_path, ".pdf")
    assert len(segments) == 1
    assert "Hello scanned world" in segments[0]["text"]


def test_gemini_ocr_model_fallback(tmp_path, monkeypatch):
    """When the primary OCR model fails, the function should try fallback models."""
    monkeypatch.setattr(config, "gemini_ocr_enabled", True)
    monkeypatch.setattr(config, "gemini_api_key", "fake-key")
    monkeypatch.setattr(config, "gemini_ocr_model", "gemini-bad-model")

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(pymupdf.Rect(10, 10, 290, 290), color=(0, 0, 0), fill=(1, 1, 1))
    pdf_path = tmp_path / "scanned_fallback.pdf"
    doc.save(str(pdf_path))
    doc.close()

    calls = []

    class GoodResponse:
        content = "Fallback OCR text"

    class BadLLM:
        def invoke(self, messages):
            error = RuntimeError("Model unavailable")
            error.code = 404
            raise error

    class GoodLLM:
        def invoke(self, messages):
            return GoodResponse()

    def mock_create_llm(model):
        calls.append(model)
        if model == "gemini-bad-model":
            return BadLLM()
        return GoodLLM()

    monkeypatch.setattr("app.services.ai.create_llm", mock_create_llm)

    segments = extract_text(pdf_path, ".pdf")
    # Primary model should have been tried and failed; a fallback should have succeeded
    assert "gemini-bad-model" in calls
    assert len(calls) >= 2
    assert len(segments) == 1
    assert "Fallback OCR text" in segments[0]["text"]


def test_health_reports_providers(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "embedding_provider" in data
    assert "storage_provider" in data
    assert "ocr_enabled" in data
    assert data["storage_provider"] == "local"


def test_docx_image_ocr(tmp_path, monkeypatch):
    """When a DOCX has no paragraph text but has embedded scanned images,
    it should extract the images and perform Gemini OCR."""
    import io
    from docx import Document

    monkeypatch.setattr(config, "gemini_ocr_enabled", True)
    monkeypatch.setattr(config, "gemini_api_key", "fake-key")

    pdf_doc = pymupdf.open()
    page = pdf_doc.new_page(width=100, height=100)
    page.draw_rect(pymupdf.Rect(10, 10, 90, 90), color=(0, 0, 0), fill=(0.8, 0.8, 0.8))
    jpeg_bytes = page.get_pixmap().tobytes("jpeg")
    pdf_doc.close()

    docx_doc = Document()
    docx_doc.add_picture(io.BytesIO(jpeg_bytes))
    docx_path = tmp_path / "scanned_invoice.docx"
    docx_doc.save(str(docx_path))

    class MockOCRResponse:
        content = "Transcribed invoice text from docx image"

    class MockLLM:
        def invoke(self, messages):
            return MockOCRResponse()

    monkeypatch.setattr("app.services.ai.create_llm", lambda model: MockLLM())

    segments = extract_text(docx_path, ".docx")
    assert len(segments) == 1
    assert "Transcribed invoice text from docx image" in segments[0]["text"]
