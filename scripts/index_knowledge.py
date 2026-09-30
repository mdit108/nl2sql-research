"""Embed semantic/*.yaml knowledge items and store them in nl2sql.knowledge_items (pgvector)."""

from app.retrieval.embeddings import get_embedder
from app.retrieval.knowledge import index_knowledge, semantic_layer_hash


def main() -> None:
    embedder = get_embedder()
    n = index_knowledge(embedder)
    print(f"Indexed {n} knowledge items with {embedder.model} (semantic layer {semantic_layer_hash()})")


if __name__ == "__main__":
    main()
