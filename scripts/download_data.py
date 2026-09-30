"""Download the Olist dataset from Kaggle into data/raw/.

Source:  https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
License: CC BY-NC-SA 4.0 (non-commercial, attribution, share-alike). Do not commit the CSVs.

Uses kagglehub, which can fetch this public dataset anonymously. If Kaggle asks for
authentication, configure your own Kaggle token (~/.kaggle/kaggle.json) or download
the zip manually from the URL above and unzip it into data/raw/.
"""

import shutil
import sys

import kagglehub

from app.config import PROJECT_ROOT

DATASET = "olistbr/brazilian-ecommerce"
EXPECTED_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_dir = kagglehub.dataset_download(DATASET)
    for name in EXPECTED_FILES:
        src = f"{cache_dir}/{name}"
        shutil.copy(src, RAW_DIR / name)
        print(f"  {name:45s} {(RAW_DIR / name).stat().st_size / 1e6:6.1f} MB")
    missing = [n for n in EXPECTED_FILES if not (RAW_DIR / n).exists()]
    if missing:
        sys.exit(f"Missing files: {missing}")
    print(f"Downloaded {len(EXPECTED_FILES)} files to {RAW_DIR}")


if __name__ == "__main__":
    main()
