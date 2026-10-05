"""Benchmark file loading and validation."""

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT

BENCHMARK_DIR = PROJECT_ROOT / "benchmark"
EXPECTED_DIR = BENCHMARK_DIR / "expected"

TAGS = {"STRUCTURAL", "RELATIONAL", "DESCRIPTIVE", "BUSINESS_IDENTITY", "METRIC_SEMANTICS",
        "DOMAIN_SEMANTICS", "AMBIGUITY", "TEMPORAL", "MULTI_HOP", "SEMANTIC_TRAP"}
CATEGORIES = {"schema", "relational", "metric", "trap", "ambiguous"}


class Comparison(BaseModel):
    order_matters: bool = False
    match_columns: list[int] | None = None  # expected-column indices that must be present; None = all
    rel_tol: float = 1e-6
    abs_tol: float = 1e-6
    percent_ok: bool = False  # accept 0.031 vs 3.1
    month_key: bool = False   # normalise dates/timestamps/'YYYY-MM' strings to 'YYYY-MM'


class Alternative(BaseModel):
    rationale: str
    sql: str
    comparison: Comparison = Field(default_factory=Comparison)


class SemanticCheck(BaseModel):
    knowledge: str
    pattern: str
    expect: str  # "present" | "absent"


class Question(BaseModel):
    id: str
    question: str
    category: str
    tags: list[str]
    difficulty: str
    expected_sql: str
    required_tables: list[str]
    required_knowledge: list[str] = Field(default_factory=list)
    related_knowledge: list[str] = Field(default_factory=list)
    comparison: Comparison = Field(default_factory=Comparison)
    alternatives: list[Alternative] = Field(default_factory=list)
    semantic_checks: list[SemanticCheck] = Field(default_factory=list)
    notes: str = ""


class Benchmark(BaseModel):
    version: str
    path: str
    hash: str
    questions: list[Question]


def load_benchmark(path: str | Path = BENCHMARK_DIR / "pilot.yaml") -> Benchmark:
    path = Path(path)
    raw = path.read_bytes()
    doc = yaml.safe_load(raw)
    questions = [Question(**q) for q in doc["questions"]]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate question ids")
    for q in questions:
        if unknown := set(q.tags) - TAGS:
            raise ValueError(f"{q.id}: unknown tags {unknown}")
        if q.category not in CATEGORIES:
            raise ValueError(f"{q.id}: unknown category {q.category}")
    return Benchmark(version=doc["version"], path=str(path.relative_to(PROJECT_ROOT)),
                     hash=hashlib.sha256(raw).hexdigest()[:12], questions=questions)


def load_expected(question_id: str) -> dict:
    """Ground truth written by `python -m evaluation.ground_truth`."""
    path = EXPECTED_DIR / f"{question_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `python -m evaluation.ground_truth`")
    return json.loads(path.read_text())
