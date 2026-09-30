"""Data-quality report for the loaded olist schema.

Writes data/reports/data_quality.md with row counts, null counts, duplicates,
referential checks (including soft joins without FKs), date ranges and distinct counts.
"""

from sqlalchemy import text

from app.config import PROJECT_ROOT
from app.database import owner_engine
from app.database.fingerprint import TABLES, database_fingerprint

REPORT = PROJECT_ROOT / "data" / "reports" / "data_quality.md"

# name -> SQL returning a count; each should be 0 unless noted as a known quirk.
DUPLICATE_CHECKS = {
    "customer_unique_id with >1 customer_id (expected: repeat buyers)":
        "SELECT count(*) FROM (SELECT customer_unique_id FROM olist.customers "
        "GROUP BY 1 HAVING count(*) > 1) x",
    "review_id reused across orders (known source quirk)":
        "SELECT count(*) FROM (SELECT review_id FROM olist.order_reviews GROUP BY 1 HAVING count(*) > 1) x",
    "orders with >1 review":
        "SELECT count(*) FROM (SELECT order_id FROM olist.order_reviews GROUP BY 1 HAVING count(*) > 1) x",
}

REFERENTIAL_CHECKS = {
    "orders without items": "SELECT count(*) FROM olist.orders o WHERE NOT EXISTS "
                            "(SELECT 1 FROM olist.order_items i WHERE i.order_id = o.order_id)",
    "orders without payments": "SELECT count(*) FROM olist.orders o WHERE NOT EXISTS "
                               "(SELECT 1 FROM olist.order_payments p WHERE p.order_id = o.order_id)",
    "orders without reviews": "SELECT count(*) FROM olist.orders o WHERE NOT EXISTS "
                              "(SELECT 1 FROM olist.order_reviews r WHERE r.order_id = o.order_id)",
    "products without category": "SELECT count(*) FROM olist.products WHERE product_category_name IS NULL",
    "customer zip prefixes missing from geolocation (soft join, no FK)":
        "SELECT count(*) FROM olist.customers c WHERE NOT EXISTS (SELECT 1 FROM olist.geolocation g "
        "WHERE g.geolocation_zip_code_prefix = c.customer_zip_code_prefix)",
    "seller zip prefixes missing from geolocation (soft join, no FK)":
        "SELECT count(*) FROM olist.sellers s WHERE NOT EXISTS (SELECT 1 FROM olist.geolocation g "
        "WHERE g.geolocation_zip_code_prefix = s.seller_zip_code_prefix)",
    "delivered orders with no delivery date":
        "SELECT count(*) FROM olist.orders WHERE order_status = 'delivered' "
        "AND order_delivered_customer_date IS NULL",
    "orders whose payments differ from items+freight by > 1.00":
        "SELECT count(*) FROM (SELECT o.order_id FROM olist.orders o "
        "JOIN (SELECT order_id, sum(price + freight_value) v FROM olist.order_items GROUP BY 1) i USING (order_id) "
        "JOIN (SELECT order_id, sum(payment_value) v FROM olist.order_payments GROUP BY 1) p USING (order_id) "
        "WHERE abs(i.v - p.v) > 1) x",
}

DATE_COLUMNS = {
    "orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
               "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}


def columns_of(conn, table: str) -> list[str]:
    return list(conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'olist' AND table_name = :t ORDER BY ordinal_position"), {"t": table}).scalars())


def main() -> None:
    lines = ["# Data-quality report", ""]
    fp = database_fingerprint()
    lines += [f"Database fingerprint: `{fp['hash']}` (PostgreSQL {fp['postgres_version']})", ""]

    with owner_engine().connect() as conn:
        lines += ["## Row counts", "", "| table | rows |", "|---|---:|"]
        lines += [f"| {t} | {n:,} |" for t, n in fp["row_counts"].items()]

        lines += ["", "## Nulls and distinct values", "",
                  "| table.column | nulls | distinct |", "|---|---:|---:|"]
        for table in TABLES:
            for col in columns_of(conn, table):
                nulls, distinct = conn.execute(text(
                    f"SELECT count(*) - count({col}), count(DISTINCT {col}) FROM olist.{table}")).one()
                lines.append(f"| {table}.{col} | {nulls:,} | {distinct:,} |")

        for title, checks in [("Duplicates", DUPLICATE_CHECKS), ("Referential checks", REFERENTIAL_CHECKS)]:
            lines += ["", f"## {title}", "", "| check | count |", "|---|---:|"]
            for name, sql in checks.items():
                lines.append(f"| {name} | {conn.execute(text(sql)).scalar_one():,} |")

        lines += ["", "Hard foreign keys are enforced by the schema, so FK violations are 0 by construction.",
                  "", "## Date ranges", "", "| column | min | max |", "|---|---|---|"]
        for table, cols in DATE_COLUMNS.items():
            for col in cols:
                lo, hi = conn.execute(text(f"SELECT min({col}), max({col}) FROM olist.{table}")).one()
                lines.append(f"| {table}.{col} | {lo} | {hi} |")

        lines += ["", "## Orders per month (coverage)", "", "| month | orders |", "|---|---:|"]
        for month, n in conn.execute(text(
                "SELECT to_char(date_trunc('month', order_purchase_timestamp), 'YYYY-MM'), count(*) "
                "FROM olist.orders GROUP BY 1 ORDER BY 1")):
            lines.append(f"| {month} | {n:,} |")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:16]))
    print(f"... full report: {REPORT}")


if __name__ == "__main__":
    main()
