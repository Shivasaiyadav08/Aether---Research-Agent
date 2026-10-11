"""Run from backend: python -m scripts.smoke_local. No LLM calls or API keys needed."""

from uuid import uuid4

from app.core.config import config
from app.services.vector import VectorStore


def main():
    config.data_dir.mkdir(parents=True, exist_ok=True)
    store = VectorStore(config.data_dir, config.embedding_model)
    workspace = f"smoke_{uuid4().hex}"
    try:
        store.index(
            workspace,
            "astronomy",
            "astronomy.txt",
            [{"text": "Astronomy is the scientific study of stars, planets and galaxies.", "page": 0}],
            "v1",
        )
        store.index(
            workspace,
            "baking",
            "bread.txt",
            [{"text": "Bread is baked from flour, water and yeast in a hot oven.", "page": 0}],
            "v1",
        )
        result = store.retrieve(workspace, "How do researchers study galaxies and stars?", 1)
        assert result[0]["document_id"] == "astronomy", result
        assert len(store.embed(["Evidence"])[0]) == 384
        store.delete_document(workspace, "astronomy")
        assert all(item["document_id"] != "astronomy" for item in store.retrieve(workspace, "stars"))
        print("PASS: real local MiniLM embeddings (384 dimensions), semantic retrieval, and deletion.")
    finally:
        # Only the uniquely named temporary smoke collection is removed.
        store.delete_workspace(workspace)


if __name__ == "__main__":
    main()
