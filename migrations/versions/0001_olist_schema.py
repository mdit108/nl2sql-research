"""Olist analytics schema.

Normalised version of the nine Olist CSVs. Column names follow the source
files (so they stay recognisable) except two source typos (`*_lenght`).

Revision ID: 0001
Create Date: 2026-10-01
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ORDER_STATUSES = (
    "'created','approved','invoiced','processing','shipped','delivered','canceled','unavailable'"
)
PAYMENT_TYPES = "'credit_card','boleto','voucher','debit_card','not_defined'"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS olist")

    op.execute("""
    CREATE TABLE olist.product_category_translation (
        product_category_name          text PRIMARY KEY,
        product_category_name_english  text NOT NULL,
        -- true for the 2 categories used by products but missing from the source translation file
        is_inferred                    boolean NOT NULL DEFAULT false
    )""")

    op.execute("""
    CREATE TABLE olist.geolocation (
        -- One row per zip prefix, aggregated from ~1M raw rows (median lat/lng, most common city/state).
        geolocation_zip_code_prefix  char(5) PRIMARY KEY,
        geolocation_lat              double precision NOT NULL,
        geolocation_lng              double precision NOT NULL,
        geolocation_city             text NOT NULL,
        geolocation_state            char(2) NOT NULL,
        source_row_count             integer NOT NULL
    )""")

    op.execute("""
    CREATE TABLE olist.customers (
        customer_id               char(32) PRIMARY KEY,
        customer_unique_id        char(32) NOT NULL,
        customer_zip_code_prefix  char(5) NOT NULL,
        customer_city             text NOT NULL,
        customer_state            char(2) NOT NULL
    )""")
    op.execute("CREATE INDEX ix_customers_unique_id ON olist.customers (customer_unique_id)")
    op.execute("CREATE INDEX ix_customers_state ON olist.customers (customer_state)")

    op.execute("""
    CREATE TABLE olist.sellers (
        seller_id               char(32) PRIMARY KEY,
        seller_zip_code_prefix  char(5) NOT NULL,
        seller_city             text NOT NULL,
        seller_state            char(2) NOT NULL
    )""")

    op.execute("""
    CREATE TABLE olist.products (
        product_id                  char(32) PRIMARY KEY,
        product_category_name       text REFERENCES olist.product_category_translation,
        product_name_length         integer,
        product_description_length  integer,
        product_photos_qty          integer,
        product_weight_g            integer,
        product_length_cm           integer,
        product_height_cm           integer,
        product_width_cm            integer
    )""")
    op.execute("CREATE INDEX ix_products_category ON olist.products (product_category_name)")

    op.execute(f"""
    CREATE TABLE olist.orders (
        order_id                       char(32) PRIMARY KEY,
        customer_id                    char(32) NOT NULL UNIQUE REFERENCES olist.customers,
        order_status                   text NOT NULL CHECK (order_status IN ({ORDER_STATUSES})),
        order_purchase_timestamp       timestamp NOT NULL,
        order_approved_at              timestamp,
        order_delivered_carrier_date   timestamp,
        order_delivered_customer_date  timestamp,
        order_estimated_delivery_date  timestamp NOT NULL
    )""")
    op.execute("CREATE INDEX ix_orders_purchase_ts ON olist.orders (order_purchase_timestamp)")
    op.execute("CREATE INDEX ix_orders_status ON olist.orders (order_status)")

    op.execute("""
    CREATE TABLE olist.order_items (
        order_id             char(32) NOT NULL REFERENCES olist.orders,
        order_item_id        smallint NOT NULL CHECK (order_item_id >= 1),
        product_id           char(32) NOT NULL REFERENCES olist.products,
        seller_id            char(32) NOT NULL REFERENCES olist.sellers,
        shipping_limit_date  timestamp NOT NULL,
        price                numeric(10, 2) NOT NULL CHECK (price >= 0),
        freight_value        numeric(10, 2) NOT NULL CHECK (freight_value >= 0),
        PRIMARY KEY (order_id, order_item_id)
    )""")
    op.execute("CREATE INDEX ix_order_items_product ON olist.order_items (product_id)")
    op.execute("CREATE INDEX ix_order_items_seller ON olist.order_items (seller_id)")

    op.execute(f"""
    CREATE TABLE olist.order_payments (
        order_id              char(32) NOT NULL REFERENCES olist.orders,
        payment_sequential    smallint NOT NULL CHECK (payment_sequential >= 1),
        payment_type          text NOT NULL CHECK (payment_type IN ({PAYMENT_TYPES})),
        payment_installments  smallint NOT NULL CHECK (payment_installments >= 0),
        payment_value         numeric(10, 2) NOT NULL CHECK (payment_value >= 0),
        PRIMARY KEY (order_id, payment_sequential)
    )""")

    op.execute("""
    CREATE TABLE olist.order_reviews (
        -- review_id is not unique in the source (the same review can cover several orders),
        -- so (review_id, order_id) is the natural key.
        review_id                char(32) NOT NULL,
        order_id                 char(32) NOT NULL REFERENCES olist.orders,
        review_score             smallint NOT NULL CHECK (review_score BETWEEN 1 AND 5),
        review_comment_title     text,
        review_comment_message   text,
        review_creation_date     timestamp NOT NULL,
        review_answer_timestamp  timestamp NOT NULL,
        PRIMARY KEY (review_id, order_id)
    )""")
    op.execute("CREATE INDEX ix_order_reviews_order ON olist.order_reviews (order_id)")


def downgrade() -> None:
    op.execute("DROP SCHEMA olist CASCADE")
