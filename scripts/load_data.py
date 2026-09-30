"""Load the Olist CSVs from data/raw/ into the olist schema.

Steps: validate input files -> transform -> TRUNCATE -> COPY. Idempotent.
Run `alembic upgrade head` first (tables and indexes come from migrations).
"""

import io
import sys
import time

import pandas as pd

from app.config import PROJECT_ROOT
from app.database import owner_engine

RAW = PROJECT_ROOT / "data" / "raw"

# Source header -> expected columns (validated before anything is loaded).
SOURCES = {
    "customers": ("olist_customers_dataset.csv", [
        "customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]),
    "sellers": ("olist_sellers_dataset.csv", [
        "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]),
    "products": ("olist_products_dataset.csv", [
        "product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
        "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]),
    "orders": ("olist_orders_dataset.csv", [
        "order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]),
    "order_items": ("olist_order_items_dataset.csv", [
        "order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"]),
    "order_payments": ("olist_order_payments_dataset.csv", [
        "order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"]),
    "order_reviews": ("olist_order_reviews_dataset.csv", [
        "review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
        "review_creation_date", "review_answer_timestamp"]),
    "geolocation": ("olist_geolocation_dataset.csv", [
        "geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city",
        "geolocation_state"]),
    "product_category_translation": ("product_category_name_translation.csv", [
        "product_category_name", "product_category_name_english"]),
}

# Categories used by products but absent from the translation file (translated by us).
MISSING_TRANSLATIONS = {
    "pc_gamer": "pc_gamer",
    "portateis_cozinha_e_preparadores_de_alimentos": "portable_kitchen_and_food_preparers",
}

# Parents before children so foreign keys hold.
LOAD_ORDER = [
    "product_category_translation", "geolocation", "customers", "sellers", "products",
    "orders", "order_items", "order_payments", "order_reviews",
]


def read_and_validate() -> dict[str, pd.DataFrame]:
    frames = {}
    for table, (filename, columns) in SOURCES.items():
        path = RAW / filename
        if not path.exists():
            sys.exit(f"Missing {path}. Run `python scripts/download_data.py` first.")
        # Read as strings: zip prefixes have leading zeros and ids must not be coerced.
        df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        if list(df.columns) != columns:
            sys.exit(f"{filename}: unexpected header {list(df.columns)}")
        frames[table] = df
        print(f"  read {filename:45s} {len(df):>9,} rows")
    return frames


def transform(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = dict(frames)

    t = frames["product_category_translation"].assign(is_inferred=False)
    extra = pd.DataFrame(
        [{"product_category_name": k, "product_category_name_english": v, "is_inferred": True}
         for k, v in MISSING_TRANSLATIONS.items()]
    )
    out["product_category_translation"] = pd.concat([t, extra], ignore_index=True)

    out["products"] = frames["products"].rename(columns={
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    })

    # ~1M raw rows with repeated prefixes -> one row per prefix.
    g = frames["geolocation"].copy()
    g["geolocation_lat"] = g["geolocation_lat"].astype(float)
    g["geolocation_lng"] = g["geolocation_lng"].astype(float)
    grouped = g.groupby("geolocation_zip_code_prefix")
    out["geolocation"] = pd.DataFrame({
        "geolocation_lat": grouped["geolocation_lat"].median(),
        "geolocation_lng": grouped["geolocation_lng"].median(),
        "geolocation_city": grouped["geolocation_city"].agg(lambda s: s.mode().iat[0]),
        "geolocation_state": grouped["geolocation_state"].agg(lambda s: s.mode().iat[0]),
        "source_row_count": grouped.size(),
    }).reset_index()

    return out


def copy_frame(cursor, table: str, df: pd.DataFrame) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    columns = ", ".join(df.columns)
    with cursor.copy(f"COPY olist.{table} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as copy:
        copy.write(buf.read())


def main() -> None:
    print("Reading and validating CSVs")
    frames = transform(read_and_validate())

    raw = owner_engine().raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute("TRUNCATE " + ", ".join(f"olist.{t}" for t in LOAD_ORDER) + " CASCADE")
            for table in LOAD_ORDER:
                start = time.perf_counter()
                copy_frame(cur, table, frames[table])
                print(f"  loaded olist.{table:30s} {len(frames[table]):>9,} rows "
                      f"({time.perf_counter() - start:.1f}s)")
            for table in LOAD_ORDER:
                cur.execute(f"ANALYZE olist.{table}")
        raw.commit()
    finally:
        raw.close()
    print("Done. Next: python scripts/validate_data.py")


if __name__ == "__main__":
    main()
