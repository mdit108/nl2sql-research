"""A cheap identity for "which data is loaded", stored with every ground truth and run."""

import hashlib

from sqlalchemy import text

from app.database import owner_engine

TABLES = [
    "customers", "geolocation", "order_items", "order_payments", "order_reviews",
    "orders", "product_category_translation", "products", "sellers",
]


def database_fingerprint() -> dict:
    with owner_engine().connect() as conn:
        counts = {t: conn.execute(text(f"SELECT count(*) FROM olist.{t}")).scalar_one() for t in TABLES}
        # Money columns change if the data or the loader's transform changes.
        checksum = conn.execute(text(
            "SELECT sum(price)::text || '/' || sum(freight_value)::text FROM olist.order_items"
        )).scalar_one()
        pg_version = conn.execute(text("SHOW server_version")).scalar_one()
    digest = hashlib.sha256(f"{sorted(counts.items())}|{checksum}".encode()).hexdigest()[:12]
    return {"hash": digest, "row_counts": counts, "postgres_version": pg_version}
