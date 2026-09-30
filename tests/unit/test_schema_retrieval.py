"""Schema context is rendered from structured metadata (no DB needed for these tests)."""

from app.nl2sql.schema import Column, Table, render_schema

TABLES = (
    Table("orders", [Column("order_id", "char(32)", is_pk=True),
                     Column("customer_id", "char(32)", references="customers.customer_id")]),
)
DESCRIPTIONS = {"orders": {"description": "One row per order.",
                           "columns": {"order_id": "Unique identifier of the order."}}}
RELATIONSHIPS = [{"from": "orders.customer_id", "to": "customers.customer_id", "cardinality": "one-to-one"}]


def test_e1_has_names_and_types_only():
    text = render_schema(TABLES, relational=False, descriptive=False)
    assert "order_id char(32)" in text
    assert "PK" not in text and "FK" not in text and "--" not in text


def test_e2_adds_keys_and_relationships():
    text = render_schema(TABLES, True, False, relationships=RELATIONSHIPS)
    assert "order_id char(32) PK" in text
    assert "FK -> customers.customer_id" in text
    assert "orders.customer_id -> customers.customer_id (one-to-one)" in text
    assert "One row per order" not in text


def test_e3_adds_descriptions():
    text = render_schema(TABLES, True, True, DESCRIPTIONS, RELATIONSHIPS)
    assert "TABLE orders  -- One row per order." in text
    assert "-- Unique identifier of the order." in text
