import pytest

from app.llm import MockProvider
from app.nl2sql.pipeline import NL2SQLPipeline

pytestmark = pytest.mark.integration

GOOD = "SELECT COUNT(DISTINCT customer_unique_id) FROM customers"


@pytest.fixture(scope="module")
def pipeline():
    return NL2SQLPipeline(MockProvider({"How many customers": GOOD}))


@pytest.mark.parametrize("level", ["E0", "E1", "E2", "E3", "E4", "E5", "E6"])
def test_every_level_runs_end_to_end(pipeline, level):
    trace = pipeline.run("How many customers are there?", level)
    assert trace.sql_valid and trace.execution_success
    assert trace.rows == [[96096]]
    assert (len(trace.retrieved) > 0) == (level in {"E4", "E5", "E6"})


def test_context_grows_monotonically(pipeline):
    sizes = [len(pipeline.run("How many customers are there?", lv).prompt) for lv in
             ["E0", "E1", "E2", "E3", "E4", "E5", "E6"]]
    assert sizes == sorted(sizes)


def test_retrieval_finds_customer_definition(pipeline):
    trace = pipeline.run("How many customers are there?", "E4")
    assert "ent.customer" in [i.id for i in trace.retrieved]
    assert all(i.knowledge_type == "business_entity" for i in trace.retrieved)


def test_gold_mode_uses_given_items_only(pipeline):
    trace = pipeline.run("How many customers are there?", "E6", mode="gold",
                         gold_ids=["ent.customer", "met.revenue"])
    assert [i.id for i in trace.retrieved] == ["ent.customer", "met.revenue"]
    assert trace.context_mode == "gold"


def test_unsafe_sql_is_never_executed():
    p = NL2SQLPipeline(MockProvider(default="DELETE FROM orders"))
    trace = p.run("Delete everything", "E1")
    assert not trace.sql_valid and trace.validation_stage == "safety"
    assert trace.execution_latency_ms == 0.0
