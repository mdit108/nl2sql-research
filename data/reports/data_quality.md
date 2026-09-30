# Data-quality report

Database fingerprint: `f2b0526aa07e` (PostgreSQL 17.11 (Homebrew))

## Row counts

| table | rows |
|---|---:|
| customers | 99,441 |
| geolocation | 19,015 |
| order_items | 112,650 |
| order_payments | 103,886 |
| order_reviews | 99,224 |
| orders | 99,441 |
| product_category_translation | 73 |
| products | 32,951 |
| sellers | 3,095 |

## Nulls and distinct values

| table.column | nulls | distinct |
|---|---:|---:|
| customers.customer_id | 0 | 99,441 |
| customers.customer_unique_id | 0 | 96,096 |
| customers.customer_zip_code_prefix | 0 | 14,994 |
| customers.customer_city | 0 | 4,119 |
| customers.customer_state | 0 | 27 |
| geolocation.geolocation_zip_code_prefix | 0 | 19,015 |
| geolocation.geolocation_lat | 0 | 18,991 |
| geolocation.geolocation_lng | 0 | 18,990 |
| geolocation.geolocation_city | 0 | 5,829 |
| geolocation.geolocation_state | 0 | 27 |
| geolocation.source_row_count | 0 | 483 |
| order_items.order_id | 0 | 98,666 |
| order_items.order_item_id | 0 | 21 |
| order_items.product_id | 0 | 32,951 |
| order_items.seller_id | 0 | 3,095 |
| order_items.shipping_limit_date | 0 | 93,318 |
| order_items.price | 0 | 5,968 |
| order_items.freight_value | 0 | 6,999 |
| order_payments.order_id | 0 | 99,440 |
| order_payments.payment_sequential | 0 | 29 |
| order_payments.payment_type | 0 | 5 |
| order_payments.payment_installments | 0 | 24 |
| order_payments.payment_value | 0 | 29,077 |
| order_reviews.review_id | 0 | 98,410 |
| order_reviews.order_id | 0 | 98,673 |
| order_reviews.review_score | 0 | 5 |
| order_reviews.review_comment_title | 87,656 | 4,527 |
| order_reviews.review_comment_message | 58,247 | 36,159 |
| order_reviews.review_creation_date | 0 | 636 |
| order_reviews.review_answer_timestamp | 0 | 98,248 |
| orders.order_id | 0 | 99,441 |
| orders.customer_id | 0 | 99,441 |
| orders.order_status | 0 | 8 |
| orders.order_purchase_timestamp | 0 | 98,875 |
| orders.order_approved_at | 160 | 90,733 |
| orders.order_delivered_carrier_date | 1,783 | 81,018 |
| orders.order_delivered_customer_date | 2,965 | 95,664 |
| orders.order_estimated_delivery_date | 0 | 459 |
| product_category_translation.product_category_name | 0 | 73 |
| product_category_translation.product_category_name_english | 0 | 73 |
| product_category_translation.is_inferred | 0 | 2 |
| products.product_id | 0 | 32,951 |
| products.product_category_name | 610 | 73 |
| products.product_name_length | 610 | 66 |
| products.product_description_length | 610 | 2,960 |
| products.product_photos_qty | 610 | 19 |
| products.product_weight_g | 2 | 2,204 |
| products.product_length_cm | 2 | 99 |
| products.product_height_cm | 2 | 102 |
| products.product_width_cm | 2 | 95 |
| sellers.seller_id | 0 | 3,095 |
| sellers.seller_zip_code_prefix | 0 | 2,246 |
| sellers.seller_city | 0 | 611 |
| sellers.seller_state | 0 | 23 |

## Duplicates

| check | count |
|---|---:|
| customer_unique_id with >1 customer_id (expected: repeat buyers) | 2,997 |
| review_id reused across orders (known source quirk) | 789 |
| orders with >1 review | 547 |

## Referential checks

| check | count |
|---|---:|
| orders without items | 775 |
| orders without payments | 1 |
| orders without reviews | 768 |
| products without category | 610 |
| customer zip prefixes missing from geolocation (soft join, no FK) | 278 |
| seller zip prefixes missing from geolocation (soft join, no FK) | 7 |
| delivered orders with no delivery date | 8 |
| orders whose payments differ from items+freight by > 1.00 | 249 |

Hard foreign keys are enforced by the schema, so FK violations are 0 by construction.

## Date ranges

| column | min | max |
|---|---|---|
| orders.order_purchase_timestamp | 2016-09-04 21:15:19 | 2018-10-17 17:30:18 |
| orders.order_approved_at | 2016-09-15 12:16:38 | 2018-09-03 17:40:06 |
| orders.order_delivered_carrier_date | 2016-10-08 10:34:01 | 2018-09-11 19:48:28 |
| orders.order_delivered_customer_date | 2016-10-11 13:46:32 | 2018-10-17 13:22:46 |
| orders.order_estimated_delivery_date | 2016-09-30 00:00:00 | 2018-11-12 00:00:00 |
| order_items.shipping_limit_date | 2016-09-19 00:15:34 | 2020-04-09 22:35:08 |
| order_reviews.review_creation_date | 2016-10-02 00:00:00 | 2018-08-31 00:00:00 |
| order_reviews.review_answer_timestamp | 2016-10-07 18:32:28 | 2018-10-29 12:27:35 |

## Orders per month (coverage)

| month | orders |
|---|---:|
| 2016-09 | 4 |
| 2016-10 | 324 |
| 2016-12 | 1 |
| 2017-01 | 800 |
| 2017-02 | 1,780 |
| 2017-03 | 2,682 |
| 2017-04 | 2,404 |
| 2017-05 | 3,700 |
| 2017-06 | 3,245 |
| 2017-07 | 4,026 |
| 2017-08 | 4,331 |
| 2017-09 | 4,285 |
| 2017-10 | 4,631 |
| 2017-11 | 7,544 |
| 2017-12 | 5,673 |
| 2018-01 | 7,269 |
| 2018-02 | 6,728 |
| 2018-03 | 7,211 |
| 2018-04 | 6,939 |
| 2018-05 | 6,873 |
| 2018-06 | 6,167 |
| 2018-07 | 6,292 |
| 2018-08 | 6,512 |
| 2018-09 | 16 |
| 2018-10 | 4 |
