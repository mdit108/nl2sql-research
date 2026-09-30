from evaluation.benchmark import load_benchmark
from evaluation.failures import classify

QUESTIONS = {q.id: q for q in load_benchmark().questions}


def record(sql, valid=True, stage=None, executed=True, error_type=None, plausible=False):
    return {"generated_sql": sql, "sql_valid": valid, "validation_stage": stage, "execution_success": executed,
            "execution_error_type": error_type, "correct": False, "correct_plausible": plausible}


def test_syntax_and_execution_errors():
    q = QUESTIONS["p01"]
    assert classify(q, record("SELEC", valid=False, stage="syntax"))[0] == "SQL_SYNTAX"
    assert classify(q, record("SELECT * FROM x", valid=False, stage="schema"))[0] == "WRONG_TABLE"
    assert classify(q, record("SELECT foo FROM orders", executed=False, error_type="UndefinedColumn"))[0] == "WRONG_COLUMN"
    assert classify(q, record("SELECT 1/0", executed=False, error_type="DivisionByZero"))[0] == "EXECUTION_ERROR"


def test_customer_identity_trap_is_business_semantics():
    category, rule = classify(QUESTIONS["p14"], record("SELECT COUNT(*) FROM customers"))
    assert category == "BUSINESS_SEMANTICS"
    assert "ent.customer" in rule


def test_revenue_from_payments_is_metric_definition():
    sql = ("SELECT SUM(p.payment_value) FROM order_payments p JOIN orders o USING (order_id) "
           "WHERE o.order_status NOT IN ('canceled') AND o.order_purchase_timestamp >= '2017-01-01'")
    assert classify(QUESTIONS["p09"], record(sql))[0] == "METRIC_DEFINITION"


def test_alternative_interpretation_is_business_semantics():
    assert classify(QUESTIONS["p19"], record("SELECT 1", plausible=True))[0] == "BUSINESS_SEMANTICS"


def test_wrong_aggregation():
    # AOV computed as average item price.
    sql = ("SELECT AVG(i.price) FROM order_items i JOIN orders o ON o.order_id = i.order_id "
           "WHERE o.order_status NOT IN ('canceled', 'unavailable')")
    assert classify(QUESTIONS["p10"], record(sql))[0] == "WRONG_AGGREGATION"


def test_missing_table():
    sql = "SELECT COUNT(*) FROM order_items WHERE seller_id IS NOT NULL"
    assert classify(QUESTIONS["p05"], record(sql))[0] == "WRONG_TABLE"
