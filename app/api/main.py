"""FastAPI service.  Run: uvicorn app.api.main:app --reload"""

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.database import readonly_engine
from app.llm import get_llm
from app.nl2sql.context import LEVELS
from app.nl2sql.pipeline import NL2SQLPipeline, Trace
from app.nl2sql.schema import load_descriptions, load_schema
from app.retrieval.knowledge import load_knowledge_items

app = FastAPI(title="NL2SQL research platform", version="0.1.0")


@lru_cache
def pipeline() -> NL2SQLPipeline:
    return NL2SQLPipeline(get_llm())


class QueryRequest(BaseModel):
    question: str
    level: str = "E6"
    context_mode: str = "retrieved"  # "retrieved" | "gold" (gold needs knowledge_ids)
    top_k: int | None = None
    knowledge_ids: list[str] | None = None


@app.post("/api/v1/query", response_model=Trace)
def query(req: QueryRequest) -> Trace:
    if req.level not in LEVELS:
        raise HTTPException(400, f"level must be one of {sorted(LEVELS)}")
    return pipeline().run(req.question, req.level, req.context_mode,
                          req.top_k or get_settings().retrieval_top_k, req.knowledge_ids)


@app.get("/api/v1/schema")
def schema() -> dict:
    descriptions = load_descriptions()
    return {t.name: {"description": descriptions.get(t.name, {}).get("description"),
                     "columns": [c.__dict__ for c in t.columns]} for t in load_schema()}


@app.get("/api/v1/metrics")
def metrics() -> list[dict]:
    return [{"id": i.id, "name": i.name, "definition": i.content, **i.metadata}
            for i in load_knowledge_items() if i.knowledge_type == "metric"]


@app.get("/api/v1/health")
def health() -> dict:
    try:
        with readonly_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception as e:  # noqa: BLE001
        db = f"error: {type(e).__name__}"
    s = get_settings()
    return {"status": "ok" if db == "ok" else "degraded", "database": db,
            "llm_provider": s.llm_provider, "llm_model": s.llm_model, "embedding_model": s.embedding_model}
