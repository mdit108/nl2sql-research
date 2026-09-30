import pytest
from sqlalchemy import text

from app.database import owner_engine, readonly_engine
from app.nl2sql.sql import execute_sql

pytestmark = pytest.mark.integration


def test_expected_row_counts():
    with owner_engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM olist.orders")).scalar_one() == 99441
        assert conn.execute(text("SELECT count(DISTINCT customer_unique_id) FROM olist.customers")).scalar_one() == 96096


@pytest.mark.parametrize("sql", [
    "CREATE TABLE olist.x (a int)",
    "DELETE FROM olist.orders",
    "UPDATE olist.orders SET order_status = 'canceled'",
])
def test_readonly_role_cannot_write(sql):
    """Even with the validator bypassed, the executor role cannot change data."""
    with readonly_engine().connect() as conn:
        with pytest.raises(Exception):
            conn.execute(text(sql))


def test_readonly_role_cannot_see_knowledge_store():
    with readonly_engine().connect() as conn:
        with pytest.raises(Exception):
            conn.execute(text("SELECT * FROM nl2sql.knowledge_items"))


def test_execute_sql_reports_errors_as_data():
    result = execute_sql("SELECT no_such_column FROM orders")
    assert not result.success and result.error_type == "UndefinedColumn"
    ok = execute_sql("SELECT order_status, count(*) FROM orders GROUP BY 1")
    assert ok.success and ok.row_count == 8
