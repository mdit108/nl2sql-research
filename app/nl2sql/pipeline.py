"""question -> context -> prompt -> LLM -> SQL -> validate -> execute, returning one structured trace."""

import time
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from app.llm import LLMProvider
from app.nl2sql.context import build_context
from app.nl2sql.prompt import load_prompt
from app.nl2sql.schema import table_names
from app.nl2sql.sql import execute_sql, extract_sql, validate_sql
from app.retrieval.knowledge import KnowledgeRetriever


class RetrievedItem(BaseModel):
    id: str
    knowledge_type: str
    similarity: float | None


class Trace(BaseModel):
    request_id: str
    timestamp: str
    question: str
    level: str
    context_mode: str
    top_k: int | None
    prompt_version: str
    prompt_hash: str
    prompt: str
    retrieved: list[RetrievedItem]
    retrieval_latency_ms: float
    model: str
    llm_output: str
    input_tokens: int | None
    output_tokens: int | None
    llm_latency_ms: float
    generated_sql: str
    sql_valid: bool
    validation_stage: str | None
    validation_error: str | None
    tables_used: list[str]
    corrected_sql: str | None = None  # E8 (not built yet)
    execution_success: bool
    execution_error: str | None
    execution_error_type: str | None
    execution_latency_ms: float
    columns: list[str]
    rows: list[list]
    row_count: int
    total_latency_ms: float


class NL2SQLPipeline:
    def __init__(self, llm: LLMProvider, retriever: KnowledgeRetriever | None = None,
                 prompt_version: str = "generation/v1"):
        self.llm = llm
        self.retriever = retriever
        self.prompt = load_prompt(prompt_version)

    def run(self, question: str, level: str, mode: str = "retrieved", top_k: int = 3,
            gold_ids: list[str] | None = None) -> Trace:
        start = time.perf_counter()
        if self.retriever is None and level not in ("E0", "E1", "E2", "E3") and mode == "retrieved":
            self.retriever = KnowledgeRetriever()
        context = build_context(question, level, mode, top_k, gold_ids, self.retriever)
        prompt = self.prompt.render(question, context.text)

        llm = self.llm.generate(prompt)
        sql = extract_sql(llm.text)
        validation = validate_sql(sql, table_names())
        if validation.valid:
            execution = execute_sql(sql)
        else:
            execution = None

        r = context.retrieval
        return Trace(
            request_id=uuid.uuid4().hex[:12],
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            question=question, level=level,
            context_mode=r.mode if r else "none", top_k=r.top_k if r else None,
            prompt_version=self.prompt.version, prompt_hash=self.prompt.hash, prompt=prompt,
            retrieved=[RetrievedItem(id=i.id, knowledge_type=i.knowledge_type, similarity=i.similarity)
                       for i in (r.items if r else [])],
            retrieval_latency_ms=round(r.latency_ms, 1) if r else 0.0,
            model=llm.model, llm_output=llm.text, input_tokens=llm.input_tokens, output_tokens=llm.output_tokens,
            llm_latency_ms=round(llm.latency_ms, 1),
            generated_sql=sql, sql_valid=validation.valid, validation_stage=validation.stage,
            validation_error=validation.error, tables_used=validation.tables,
            execution_success=bool(execution and execution.success),
            execution_error=execution.error if execution else None,
            execution_error_type=execution.error_type if execution else None,
            execution_latency_ms=round(execution.latency_ms, 1) if execution else 0.0,
            columns=execution.columns if execution else [], rows=execution.rows if execution else [],
            row_count=execution.row_count if execution else 0,
            total_latency_ms=round((time.perf_counter() - start) * 1000, 1),
        )
