# Dataset: Brazilian E-Commerce Public Dataset by Olist

- **Source:** https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce (published by Olist)
- **License:** CC BY-NC-SA 4.0 — non-commercial use, attribution required, share-alike.
  The CSVs are **not committed** to this repository (`data/raw/` is git-ignored); download them yourself.
- **Contents:** 9 CSV files, ~126 MB, ~99k anonymised orders from 2016-09 to 2018-10.

## Download

```bash
python scripts/download_data.py
```

This uses `kagglehub`, which can fetch this public dataset without an account. If Kaggle asks
for authentication, create your own Kaggle API token (`~/.kaggle/kaggle.json`), or download the
zip manually from the URL above and unzip the 9 CSVs into `data/raw/`.

## Why this dataset suits NL2SQL research

A realistic relational schema (orders, line items, payments, reviews, products, sellers, customers)
with business semantics that the column names alone don't give away:

- `customer_id` is per order; the person is `customer_unique_id` (99,441 vs 96,096).
- "Revenue" could be `price`, `price + freight`, or `payment_value`.
- Reviews and payments fan out when joined to order items.
- Canceled/unavailable orders exist; category names are Portuguese.

## Known quirks (measured by `scripts/validate_data.py`, see `data/reports/data_quality.md`)

| Quirk | Handling |
|---|---|
| `review_id` reused across 789 orders | primary key is (`review_id`, `order_id`) |
| 547 orders have more than one review | documented in the semantic layer |
| 2 categories missing from the translation file | added to `product_category_translation` with `is_inferred = true` |
| 610 products have no category | `product_category_name` is nullable |
| Geolocation: 1M rows, repeated zip prefixes | aggregated to one row per prefix (median lat/lng, most common city/state) |
| 278 customer / 7 seller zip prefixes missing from geolocation | soft join, no foreign key |
| Source typos `product_name_lenght`, `product_description_lenght` | renamed to `*_length` |
| 2016 and 2018-09/10 are sparse | documented in `semantic/domain_rules.yaml` |

`processed/` is reserved for derived files; nothing is written there yet.
