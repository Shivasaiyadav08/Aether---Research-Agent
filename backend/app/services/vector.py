"""This file defines the VectorStore class in Aether AI. It converts document chunks and user questions into numerical vectors (embeddings), stores document vectors in ChromaDB, and retrieves relevant chunks when the user asks a question."""
from threading import RLock

import chromadb


class VectorStore:
    """One persistent collection per workspace; the local model loads only when needed."""
#Initializes ChromaDB storage, the embedding model settings, and a lock for safe access.
    def __init__(self, data_dir, model_name, embedder=None):
        self.client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
        self.model_name = model_name
        self.model_cache = str(data_dir / "models")
        self.model = embedder
        self.lock = RLock()
#Converts text into numerical vectors using Sentence Transformers. Loads the model only when needed.
    def embed(self, texts):
        if self.model is None:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(self.model_name, cache_folder=self.model_cache)
        return self.model.encode(texts, normalize_embeddings=True).tolist()
#Gets or creates a separate ChromaDB collection for a workspace.
    def collection(self, workspace_id):
        return self.client.get_or_create_collection(
            name=f"ws_{workspace_id}", configuration={"hnsw": {"space": "cosine"}}, embedding_function=None
        )
#Stores document chunks, their embeddings, and metadata in ChromaDB.
    def index(self, workspace_id, document_id, name, chunks, version):
        with self.lock:
            collection = self.collection(workspace_id)
            # Batches keep memory bounded and stay below Chroma's maximum batch size.
            for offset in range(0, len(chunks), 64):
                batch = chunks[offset : offset + 64]
                collection.add(
                    ids=[f"{document_id}:{version}:{offset + i}" for i in range(len(batch))],
                    documents=[item["text"] for item in batch],
                    embeddings=self.embed([item["text"] for item in batch]),
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
#Converts a question into an embedding and searches for the most similar document chunks.
    def retrieve(self, workspace_id, question, count=6):
        with self.lock:
            collection = self.collection(workspace_id)
            if collection.count() == 0:
                return []
            result = collection.query(
                query_embeddings=self.embed([question]), n_results=min(count, collection.count())
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
#Deletes all indexed chunks for a document, or only a specified version.
    def delete_document(self, workspace_id, document_id, version=None):
        with self.lock:
            where = {"document_id": document_id}
            if version:
                where = {"$and": [{"document_id": document_id}, {"version": version}]}
            self.collection(workspace_id).delete(where=where)
#Deletes the entire ChromaDB collection for a workspace.
    def delete_workspace(self, workspace_id):
        with self.lock:
            if f"ws_{workspace_id}" in [item.name for item in self.client.list_collections()]:
                self.client.delete_collection(f"ws_{workspace_id}")


# 1. User uploads PDF

# 2. document.py
# Extracts text and checks for duplicates

# 3A. SQL database
# Saves the document record and extracted text


# 3B. vector.py
# Creates embeddings and indexes text chunks in ChromaDB



# 4. User asks a question
# vector.py retrieves relevant chunks; the AI workflow uses them to answer.