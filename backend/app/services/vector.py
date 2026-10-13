import logging
from threading import RLock

import chromadb

from app.core.config import config
from app.core.memory import check_and_collect_garbage, log_stage_memory

logger = logging.getLogger("aether.vector")
_MODEL_LOCK = RLock()
_SHARED_EMBEDDER = None


class VectorStore:
    """One persistent collection per workspace; the local model loads lazily and safely."""

    def __init__(self, data_dir, model_name, embedder=None):
        self.client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
        self.model_name = model_name
        self.model_cache = str(data_dir / "models")
        self.model = embedder
        self.lock = RLock()

    def _get_model(self):
        """Thread-safe singleton lazy loader for the embedding model."""
        global _SHARED_EMBEDDER
        if self.model is not None:
            return self.model
        with _MODEL_LOCK:
            if self.model is not None:
                return self.model
            if _SHARED_EMBEDDER is not None:
                self.model = _SHARED_EMBEDDER
                return self.model

            if config.embedding_provider == "gemini":
                log_stage_memory("before_model_load", provider="gemini")
                from langchain_google_genai import GoogleGenerativeAIEmbeddings

                loaded = GoogleGenerativeAIEmbeddings(
                    model="models/text-embedding-004",
                    google_api_key=config.gemini_api_key,
                )
                _SHARED_EMBEDDER = loaded
                self.model = loaded
                log_stage_memory("after_model_load", provider="gemini")
                return self.model

            log_stage_memory("before_model_load", model=self.model_name)
            import torch

            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)

            from sentence_transformers import SentenceTransformer

            loaded = SentenceTransformer(self.model_name, cache_folder=self.model_cache, device="cpu")
            if hasattr(loaded, "eval"):
                loaded.eval()

            _SHARED_EMBEDDER = loaded
            self.model = loaded
            log_stage_memory("after_model_load", model=self.model_name)
            return self.model

    def embed(self, texts):
        """Convert text into numerical vectors using Sentence Transformers, Gemini, or injected embedder."""
        if not texts:
            return []
        model = self._get_model()
        batch_size = min(len(texts), config.embedding_batch_size)
        if hasattr(model, "eval"):
            import torch

            with torch.inference_mode():
                return model.encode(
                    texts,
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
        if hasattr(model, "embed_documents"):
            import numpy as np

            embeddings = model.embed_documents(texts)
            return np.array(embeddings, dtype=np.float32)

        return model.encode(texts, normalize_embeddings=True)

    def collection(self, workspace_id):
        return self.client.get_or_create_collection(
            name=f"ws_{workspace_id}", configuration={"hnsw": {"space": "cosine"}}, embedding_function=None
        )

    def index(self, workspace_id, document_id, name, chunks, version):
        """Store document chunks, embeddings, and metadata in ChromaDB in bounded batches."""
        with self.lock:
            collection = self.collection(workspace_id)
            batch_size = config.embedding_batch_size
            log_stage_memory(
                "before_indexing",
                doc_id=document_id,
                total_chunks=len(chunks),
                batch_size=batch_size,
            )
            for offset in range(0, len(chunks), batch_size):
                batch = chunks[offset : offset + batch_size]
                batch_texts = [item["text"] for item in batch]
                embeddings = self.embed(batch_texts)
                collection.add(
                    ids=[f"{document_id}:{version}:{offset + i}" for i in range(len(batch))],
                    documents=batch_texts,
                    embeddings=embeddings,
                    metadatas=[
                        {
                            "document_id": document_id,
                            "name": name,
                            "page": item["page"],
                            "version": version,
                            "chunk": offset + i,
                        }
                        for i, item in enumerate(batch)
                    ],
                )
            log_stage_memory("after_indexing", doc_id=document_id, total_chunks=len(chunks))
            check_and_collect_garbage(threshold_mb=config.gc_threshold_mb)

    def retrieve(self, workspace_id, question, count=6):
        """Convert question into an embedding and search for the most similar chunks."""
        with self.lock:
            collection = self.collection(workspace_id)
            if collection.count() == 0:
                return []
            result = collection.query(
                query_embeddings=self.embed([question]),
                n_results=min(count, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            return [
                {
                    "id": f"D{i + 1}",
                    "kind": "document",
                    "text": text,
                    "similarity": round(max(0, min(1, 1 - distance)), 4),
                    **metadata,
                }
                for i, (text, metadata, distance) in enumerate(
                    zip(result["documents"][0], result["metadatas"][0], result["distances"][0])
                )
            ]

    def delete_document(self, workspace_id, document_id, version=None):
        with self.lock:
            where = {"document_id": document_id}
            if version:
                where = {"$and": [{"document_id": document_id}, {"version": version}]}
            self.collection(workspace_id).delete(where=where)

    def delete_workspace(self, workspace_id):
        with self.lock:
            try:
                self.client.delete_collection(f"ws_{workspace_id}")
            except Exception:
                pass


# 1. User uploads PDF

# 2. document.py
# Extracts text and checks for duplicates

# 3A. SQL database
# Saves the document record and extracted text


# 3B. vector.py
# Creates embeddings and indexes text chunks in ChromaDB



# 4. User asks a question
# vector.py retrieves relevant chunks; the AI workflow uses them to answer.