import pytest

from app.nl2sql.sql import execute_sql, validate_sql
from app.nl2sql.schema import table_names
from evaluation.benchmark import load_benchmark, load_expected
from evaluation.compare_results import compare_results

BENCH = load_benchmark()


def test_benchmark_is_well_formed():
    assert len(BENCH.questions) == 26
    for q in BENCH.questions:
        assert not set(q.required_knowledge) & set(q.related_knowledge), q.id
        assert q.required_tables
        if q.category == "ambiguous":
            assert q.alternatives, f"{q.id}: ambiguous questions need alternative interpretations"


@pytest.mark.integration
@pytest.mark.parametrize("q", BENCH.questions, ids=lambda q: q.id)
def test_gold_sql_is_valid_and_matches_stored_ground_truth(q):
    assert validate_sql(q.expected_sql, table_names()).valid
    result = execute_sql(q.expected_sql)
    assert result.success, result.error
    expected = load_expected(q.id)
    assert expected["rows"], f"{q.id}: empty ground truth"
    assert compare_results(expected["rows"], result.rows, q.comparison).correct
