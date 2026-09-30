"""Embedding providers: turn text into vectors for pgvector."""

from abc import ABC, abstractmethod
from functools import lru_cache

from app.config import Settings, get_settings


class EmbeddingProvider(ABC):
    model: str

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedProvider(EmbeddingProvider):
    """Local ONNX model (default BAAI/bge-small-en-v1.5, 384 dims). No key, deterministic."""

    def __init__(self, model: str):
        from fastembed import TextEmbedding

        self.model = model
        self._model = TextEmbedding(model_name=model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        # BGE models expect an instruction prefix on queries; fastembed adds it.
        return next(iter(self._model.query_embed(text))).tolist()


class OpenAICompatibleEmbeddings(EmbeddingProvider):
    """POST /embeddings on an OpenAI-compatible endpoint."""

    def __init__(self, settings: Settings):
        from openai import OpenAI

        key = settings.embedding_api_key or settings.llm_api_key
        if key is None or not key.get_secret_value():
            raise RuntimeError("EMBEDDING_API_KEY / LLM_API_KEY is not set")
        self.client = OpenAI(base_url=settings.embedding_base_url or settings.llm_base_url,
                             api_key=key.get_secret_value())
        self.model = settings.embedding_model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


@lru_cache
def get_embedder() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "fastembed":
        return FastEmbedProvider(settings.embedding_model)
    if settings.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbeddings(settings)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER {settings.embedding_provider!r}")
