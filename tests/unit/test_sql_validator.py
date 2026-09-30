import pytest

from app.nl2sql.sql import extract_sql, validate_sql

TABLES = {"orders", "customers", "order_items"}


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM orders",
    "WITH t AS (SELECT order_id FROM orders) SELECT COUNT(*) FROM t",
    "SELECT 1 UNION ALL SELECT 2",
    "SELECT * FROM olist.orders o JOIN olist.customers c ON c.customer_id = o.customer_id",
    "SELECT 'please drop table orders' AS note",   # keyword inside a string literal is fine
    "SELECT order_id AS created FROM orders",      # identifier containing a keyword
])
def test_accepts_read_only_queries(sql):
    assert validate_sql(sql, TABLES).valid


@pytest.mark.parametrize("sql,stage", [
    ("DELETE FROM orders", "safety"),
    ("UPDATE orders SET order_status = 'x'", "safety"),
    ("INSERT INTO orders VALUES (1)", "safety"),
    ("DROP TABLE orders", "safety"),
    ("TRUNCATE orders", "safety"),
    ("CREATE TABLE x (a int)", "safety"),
    ("ALTER TABLE orders ADD COLUMN x int", "safety"),
    ("GRANT SELECT ON orders TO public", "safety"),
    ("REVOKE SELECT ON orders FROM public", "safety"),
    ("SELECT 1; DROP TABLE orders", "safety"),
    ("SELECT * INTO new_table FROM orders", "safety"),
    ("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d", "safety"),
    ("SELEC * FRM orders", "syntax"),
    ("", "syntax"),
    ("SELECT * FROM invoices", "schema"),
])
def test_rejects(sql, stage):
    result = validate_sql(sql, TABLES)
    assert not result.valid
    assert result.stage == stage


def test_ctes_are_not_reported_as_unknown_tables():
    result = validate_sql("WITH first_orders AS (SELECT * FROM orders) SELECT * FROM first_orders", TABLES)
    assert result.valid and result.tables == ["orders"]


@pytest.mark.parametrize("output,expected", [
    ("```sql\nSELECT 1;\n```", "SELECT 1"),
    ("Here you go:\n```\nSELECT 2\n```", "SELECT 2"),
    ("```sql\nSELECT draft\n```\nBetter:\n```sql\nSELECT final;\n```", "SELECT final"),
    ("SELECT 3;", "SELECT 3"),
])
def test_extract_sql(output, expected):
    assert extract_sql(output) == expected
