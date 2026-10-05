"""Semantic knowledge store: YAML files -> pgvector table -> top-k cosine search.

The whole retrieval algorithm is `search()`:
    1. embed the question
    2. ORDER BY embedding <=> question_vector (cosine distance), per knowledge type
    3. return the top-k items with their similarity (1 - distance)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field

import yaml
from pgvector.psycopg import register_vector
from sqlalchemy import text

from app.config import PROJECT_ROOT
from app.database import owner_engine
from app.retrieval.embeddings import EmbeddingProvider, get_embedder

SEMANTIC_DIR = PROJECT_ROOT / "semantic"
KNOWLEDGE_FILES = ["entities.yaml", "metrics.yaml", "domain_rules.yaml"]


@dataclass
class KnowledgeItem:
    id: str
    knowledge_type: str
    name: str
    content: str
    metadata: dict = field(default_factory=dict)
    similarity: float | None = None  # set when returned by search()


@dataclass
class RetrievalResult:
    query: str
    top_k: int
    knowledge_types: list[str]
    items: list[KnowledgeItem]
    latency_ms: float
    mode: str = "retrieved"  # "retrieved" (pgvector) or "gold" (hand-picked gold items)


def load_knowledge_items() -> list[KnowledgeItem]:
    """The source of truth: YAML under semantic/."""
    items = []
    for filename in KNOWLEDGE_FILES:
        doc = yaml.safe_load((SEMANTIC_DIR / filename).read_text())
        for raw in doc["items"]:
            items.append(KnowledgeItem(id=raw["id"], knowledge_type=doc["knowledge_type"], name=raw["name"],
                                       content=" ".join(raw["content"].split()), metadata=raw.get("metadata", {})))
    return items


def semantic_layer_hash() -> str:
    """Changes whenever any semantic YAML changes; recorded in every experiment manifest."""
    h = hashlib.sha256()
    for path in sorted(SEMANTIC_DIR.glob("*.yaml")):
        h.update(path.read_bytes())
    return h.hexdigest()[:12]


def embedding_text(item: KnowledgeItem) -> str:
    return f"{item.name}. {item.content}"


def item_hash(item: KnowledgeItem) -> str:
    return hashlib.sha256((embedding_text(item) + json.dumps(item.metadata, sort_keys=True)).encode()).hexdigest()[:12]


def stale_knowledge_items(embedding_model: str) -> list[str]:
    """Ids whose YAML differs from what is indexed in pgvector (or that are missing / extra)."""
    expected = {i.id: item_hash(i) for i in load_knowledge_items()}
    with owner_engine().connect() as conn:
        indexed = dict(conn.execute(text(
            "SELECT id, content_hash FROM nl2sql.knowledge_items WHERE embedding_model = :m"),
            {"m": embedding_model}).all())
    return sorted(k for k in expected.keys() | indexed.keys() if expected.get(k) != indexed.get(k))


def index_knowledge(embedder: EmbeddingProvider | None = None) -> int:
    """(Re)build nl2sql.knowledge_items from YAML. Returns the number of items indexed."""
    embedder = embedder or get_embedder()
    items = load_knowledge_items()
    vectors = embedder.embed_documents([embedding_text(i) for i in items])
    raw = owner_engine().raw_connection()
    try:
        register_vector(raw.driver_connection)
        with raw.cursor() as cur:
            cur.execute("TRUNCATE nl2sql.knowledge_items")
            for item, vec in zip(items, vectors):
                cur.execute(
                    "INSERT INTO nl2sql.knowledge_items "
                    "(id, knowledge_type, name, content, metadata, embedding, embedding_model, content_hash) "
                    "VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s)",
                    (item.id, item.knowledge_type, item.name, item.content, json.dumps(item.metadata),
                     vec, embedder.model, item_hash(item)),
                )
        raw.commit()
    finally:
        raw.close()
    return len(items)


class KnowledgeRetriever:
    def __init__(self, embedder: EmbeddingProvider | None = None):
        self.embedder = embedder or get_embedder()

    def search(self, query: str, knowledge_types: list[str], top_k: int) -> RetrievalResult:
        """Top-k most similar items *per knowledge type*, so adding a type never displaces another."""
        start = time.perf_counter()
        vector = self.embedder.embed_query(query)
        items: list[KnowledgeItem] = []
        with owner_engine().connect() as conn:
            for ktype in knowledge_types:
                rows = conn.execute(text(
                    "SELECT id, knowledge_type, name, content, metadata, "
                    "       1 - (embedding <=> CAST(:v AS vector)) AS similarity "
                    "FROM nl2sql.knowledge_items "
                    "WHERE knowledge_type = :t AND embedding_model = :m "
                    "ORDER BY embedding <=> CAST(:v AS vector) "
                    "LIMIT :k"), {"v": str(vector), "t": ktype, "m": self.embedder.model, "k": top_k})
                items += [KnowledgeItem(id=r.id, knowledge_type=r.knowledge_type, name=r.name, content=r.content,
                                        metadata=r.metadata, similarity=round(float(r.similarity), 4)) for r in rows]
        return RetrievalResult(query=query, top_k=top_k, knowledge_types=knowledge_types, items=items,
                               latency_ms=(time.perf_counter() - start) * 1000)


def gold_items(item_ids: list[str], knowledge_types: list[str]) -> RetrievalResult:
    """Hand-picked gold context (from the benchmark), restricted to the types a level allows.

    Separates "the retriever missed it" from "the model had it and still got it wrong".
    """
    by_id = {i.id: i for i in load_knowledge_items()}
    items = [by_id[i] for i in item_ids if i in by_id and by_id[i].knowledge_type in knowledge_types]
    return RetrievalResult(query="", top_k=len(items), knowledge_types=knowledge_types, items=items,
                           latency_ms=0.0, mode="gold")
