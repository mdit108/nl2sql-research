"""Integrity of the semantic layer (no DB needed)."""

import yaml

from app.retrieval.knowledge import SEMANTIC_DIR, load_knowledge_items
from evaluation.benchmark import load_benchmark

DESCRIBED_TABLES = set(yaml.safe_load((SEMANTIC_DIR / "descriptions.yaml").read_text())["tables"])


def test_ids_are_unique_and_prefixed_by_type():
    items = load_knowledge_items()
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))
    prefix = {"business_entity": "ent.", "metric": "met.", "domain_rule": "rule."}
    for i in items:
        assert i.id.startswith(prefix[i.knowledge_type]), i.id


def test_every_metric_has_sql_definition_and_known_tables():
    for m in (i for i in load_knowledge_items() if i.knowledge_type == "metric"):
        assert m.metadata.get("sql_definition"), m.id
        assert set(m.metadata["tables"]) <= DESCRIBED_TABLES, m.id


def test_all_knowledge_items_reference_known_tables():
    for i in load_knowledge_items():
        assert set(i.metadata.get("tables", [])) <= DESCRIBED_TABLES, i.id


def test_metrics_are_self_contained():
    """A retrieved metric must not depend on a term defined only in another item."""
    for m in (i for i in load_knowledge_items() if i.knowledge_type == "metric"):
        assert "eligible" not in m.content.lower(), m.id
        if "exclud" in m.content.lower() and "status" in m.metadata.get("sql_definition", ""):
            assert "'canceled', 'unavailable'" in m.content, m.id


def test_benchmark_knowledge_ids_exist():
    ids = {i.id for i in load_knowledge_items()}
    for q in load_benchmark().questions:
        assert set(q.required_knowledge) <= ids, q.id
        assert set(q.related_knowledge) <= ids, q.id
        assert {c.knowledge for c in q.semantic_checks} <= ids, q.id
