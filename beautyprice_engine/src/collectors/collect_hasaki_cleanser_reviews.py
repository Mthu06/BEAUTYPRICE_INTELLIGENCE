"""Collect Hasaki cleanser reviews from the product rating-reviews API.

Run from project root:
    python src/collectors/collect_hasaki_cleanser_reviews.py

Inputs:
    data/processed/products.csv
    data/processed/product_categories.csv

Outputs:
    data/interim/hasaki/by_category/sua_rua_mat_reviews.csv
    data/interim/hasaki/by_category/sua_rua_mat_log.csv

The collector stores no reviewer names or user IDs. It deduplicates by
(source_product_id, review_id), saves progress after each product, and skips
review objects whose product_id conflicts with the requested product ID.
"""

from __future__ import annotations

import csv
import html
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

# Resolve paths from project root even when this file is under src/collectors.
ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_FILE = ROOT / "data" / "processed" / "products.csv"
CATEGORIES_FILE = ROOT / "data" / "processed" / "product_categories.csv"

OUTPUT_DIR = ROOT / "data" / "interim" / "hasaki" / "by_category"
OUTPUT_FILE = OUTPUT_DIR / "sua_rua_mat_reviews.csv"
LOG_FILE = OUTPUT_DIR / "sua_rua_mat_log.csv"

API_URL = "https://hasaki.vn/mobile/v3/detail/product/rating-reviews"
PAGE_SIZE = 5
REQUEST_DELAY = 1.0
MAX_RETRIES = 3

FIELDS = [
    "source",
    "source_product_id",
    "product_name",
    "review_id",
    "rating",
    "review_text",
    "review_date",
    "is_bought",
    "has_images",
    "source_url",
]
LOG_FIELDS = [
    "time",
    "hasaki_product_id",
    "product_name",
    "status",
    "api_total",
    "reviews_added",
    "reviews_skipped_product_id_mismatch",
    "message",
]


def normalize(value: object) -> str:
    value = unicodedata.normalize("NFD", str(value or "").lower())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return value.replace("đ", "d").strip()


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Redact email addresses and phone numbers in review text.
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"(?<!\w)(?:\+?84|0)(?:[\s.-]*\d){8,10}(?!\w)", "[PHONE]", text)
    return text


def extract_hasaki_id(url: object) -> str:
    path = urlparse(str(url or "")).path
    match = re.search(r"-(\d+)\.html$", path)
    if not match:
        match = re.search(r"/(\d+)\.html$", path)
    return match.group(1) if match else ""


def load_catalog() -> list[dict]:
    for path in (PRODUCTS_FILE, CATEGORIES_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {path}")

    products = pd.read_csv(PRODUCTS_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    categories = pd.read_csv(CATEGORIES_FILE, dtype=str, encoding="utf-8-sig").fillna("")

    required_product_cols = {"product_id", "product_name", "product_url"}
    required_category_cols = {"product_id", "category"}
    if not required_product_cols.issubset(products.columns):
        raise ValueError(f"products.csv cần các cột: {sorted(required_product_cols)}")
    if not required_category_cols.issubset(categories.columns):
        raise ValueError(f"product_categories.csv cần các cột: {sorted(required_category_cols)}")

    # Match the category label flexibly, ignoring Vietnamese accents/case.
    mask = categories["category"].map(lambda x: "sua rua mat" in normalize(x))
    cleanser_categories = categories.loc[mask, ["product_id", "category"]].drop_duplicates("product_id")
    if cleanser_categories.empty:
        print("Các danh mục hiện có:")
        print(categories["category"].value_counts().to_string())
        raise RuntimeError("Không tìm thấy danh mục sữa rửa mặt; dừng an toàn.")

    catalog = cleanser_categories.merge(
        products[["product_id", "product_name", "product_url"]],
        on="product_id",
        how="left",
        validate="one_to_one",
    )
    catalog["hasaki_product_id"] = catalog["product_url"].map(extract_hasaki_id)
    missing = catalog["hasaki_product_id"].eq("")
    if missing.any():
        print(f"Cảnh báo: bỏ qua {int(missing.sum())} sản phẩm không trích xuất được mã Hasaki từ URL.")

    catalog = catalog.loc[~missing].drop_duplicates("hasaki_product_id")
    if catalog.empty:
        raise RuntimeError("Không có sản phẩm sữa rửa mặt với mã Hasaki hợp lệ.")
    return catalog.to_dict("records")


def load_existing() -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    if not OUTPUT_FILE.exists():
        return rows
    with OUTPUT_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            product_id = str(row.get("source_product_id", "")).strip()
            review_id = str(row.get("review_id", "")).strip()
            if product_id and review_id:
                rows[(product_id, review_id)] = {field: row.get(field, "") for field in FIELDS}
    return rows


def save_reviews(rows: dict[tuple[str, str], dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows.values())


def append_log(product_id: str, product_name: str, status: str, total, added: int, mismatches: int, message: str = "") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not LOG_FILE.exists()
    with LOG_FILE.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "hasaki_product_id": product_id,
            "product_name": product_name,
            "status": status,
            "api_total": "" if total is None else total,
            "reviews_added": added,
            "reviews_skipped_product_id_mismatch": mismatches,
            "message": message,
        })


def fetch_json(session: requests.Session, params: dict) -> dict:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(API_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if payload.get("status", {}).get("error_code") != 0:
                raise RuntimeError("API báo lỗi: " + str(payload.get("status", {}).get("error_message")))
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
    raise RuntimeError(str(last_error))


def get_total(data: dict):
    if data.get("total") is not None:
        return int(data["total"])
    for item in data.get("rating", {}).get("filter", []):
        if item.get("key") == "filter_all":
            return int(item.get("count", 0))
    return None


def collect_product(session: requests.Session, product: dict, rows: dict) -> tuple[int, int | None, int]:
    product_id = str(product["hasaki_product_id"])
    product_name = str(product.get("product_name", "")).strip()
    product_url = str(product.get("product_url", "")).strip()
    total = None
    page = 1
    added = 0
    mismatches = 0
    seen_this_run: set[tuple[str, str]] = set()
    seen_count = 0

    while True:
        params = {
            "product_id": product_id,
            "page": page,
            "size": PAGE_SIZE,
            "sort": "create",
            "filter": "filter_all",
            "is_desktop": 1,
        }
        payload = fetch_json(session, params)
        data = payload.get("data", {})
        reviews = data.get("reviews", [])
        if not isinstance(reviews, list):
            raise RuntimeError(f"Trang {page}: data.reviews không phải danh sách")

        if total is None:
            total = get_total(data)
            print(f"  API báo tổng review: {total}")
        if not reviews:
            break

        for item in reviews:
            review_id = str(item.get("id", "")).strip()
            if not review_id:
                continue

            # The API can occasionally return a cached/adjacent product review.
            # Never attach a review to the wrong product.
            item_product_id = str(item.get("product_id", "")).strip()
            if item_product_id and item_product_id != product_id:
                mismatches += 1
                continue

            key = (product_id, review_id)
            if key in seen_this_run:
                continue
            seen_this_run.add(key)
            seen_count += 1
            if key in rows:
                continue

            rating = item.get("rating") or {}
            created_at = item.get("created_at")
            try:
                review_date = datetime.fromtimestamp(int(created_at)).isoformat(sep=" ") if created_at else ""
            except (ValueError, TypeError, OSError, OverflowError):
                review_date = ""

            rows[key] = {
                "source": "hasaki",
                "source_product_id": product_id,
                "product_name": clean_text(item.get("product_name") or product_name),
                "review_id": review_id,
                "rating": rating.get("star"),
                "review_text": clean_text(item.get("content")),
                "review_date": review_date,
                "is_bought": item.get("is_bought"),
                "has_images": bool(item.get("images") or item.get("data_images")),
                "source_url": product_url,
            }
            added += 1

        print(f"  Trang {page}: {len(reviews)} review API trả về; thêm mới {added}; tổng file {len(rows)}")

        if total is not None and seen_count >= total:
            break
        if len(reviews) < PAGE_SIZE:
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    return added, total, mismatches


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog()
    rows = load_existing()

    print("Sản phẩm sữa rửa mặt có mã Hasaki:", len(catalog))
    print("Review đã có trong file đầu ra:", len(rows))
    print("CSV:", OUTPUT_FILE)
    print("Log:", LOG_FILE)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://hasaki.vn/",
    })

    for index, product in enumerate(catalog, start=1):
        product_id = str(product["hasaki_product_id"])
        name = str(product.get("product_name", ""))
        print(f"\n[{index}/{len(catalog)}] {name} | ID {product_id}")
        try:
            added, total, mismatches = collect_product(session, product, rows)
            save_reviews(rows)
            msg = "OK"
            if mismatches:
                msg += f"; skipped {mismatches} review(s) with mismatched product_id"
            append_log(product_id, name, "success", total, added, mismatches, msg)
            print(f"  Hoàn tất. Review mới: {added}; review lệch product_id bỏ qua: {mismatches}")
        except Exception as exc:
            save_reviews(rows)
            append_log(product_id, name, "error", None, 0, 0, f"{type(exc).__name__}: {exc}")
            print(f"  LỖI: {type(exc).__name__}: {exc}")
        time.sleep(REQUEST_DELAY)

    print("\nĐÃ KẾT THÚC LƯỢT CHẠY")
    print("Số cặp sản phẩm-review duy nhất trong bộ nhớ:", len(rows))
    print("CSV:", OUTPUT_FILE.resolve())
    print("Log:", LOG_FILE.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

