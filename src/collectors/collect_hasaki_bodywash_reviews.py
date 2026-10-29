"""Collect verified Hasaki body-wash reviews from Hasaki.

Reads the processed product catalog and category mapping, resolves each
product canonical URL/ID, validates each review product_id, skips mismatched
IDs and empty review text, and deduplicates by (canonical product ID, review ID).

Original URL IDs and canonical/API IDs are kept separately in the log. URLs
that resolve to the same canonical product are logged individually, while
reviews are deduplicated to avoid double counting. Outputs use separate
_verified filenames so existing category files are not overwritten.
"""
from __future__ import annotations

import csv
import html
import logging
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Tự tìm thư mục gốc dự án để script vẫn chạy được khi đặt trong scripts/collectors
# hoặc đặt trực tiếp ở thư mục gốc dự án.
def find_project_root(script_path: Path) -> Path:
    for parent in (script_path.parent, *script_path.parents):
        if (parent / "data" / "processed" / "products.csv").exists() and \
           (parent / "data" / "processed" / "product_categories.csv").exists():
            return parent
    # Cấu trúc mặc định nếu file được đặt trong thư mục scripts/collectors.
    return script_path.parents[2] if len(script_path.parents) > 2 else script_path.parent


ROOT = find_project_root(Path(__file__).resolve())
PRODUCTS_FILE = ROOT / "data" / "processed" / "products.csv"
CATEGORIES_FILE = ROOT / "data" / "processed" / "product_categories.csv"
OUTPUT_DIR = ROOT / "data" / "interim" / "hasaki" / "by_category"
OUTPUT_FILE = OUTPUT_DIR / "body_wash_reviews_verified.csv"
LOG_FILE = OUTPUT_DIR / "body_wash_log_verified.csv"

API_URL = "https://hasaki.vn/mobile/v3/detail/product/rating-reviews"
PAGE_SIZE = 5
REQUEST_DELAY = 1.0
MAX_RETRIES = 3
MAX_PAGES = 200
TIMEOUT = 30

REVIEW_FIELDS = [
    "source", "category", "source_product_id", "product_name", "review_id", "rating",
    "review_text", "review_date", "is_bought", "has_images", "source_url",
    "original_url_id",
]
LOG_FIELDS = [
    "time", "original_url_id", "canonical_product_id", "api_product_id",
    "original_url", "canonical_url", "product_name", "status", "api_total",
    "reviews_added", "reviews_skipped_product_id_mismatch", "reviews_skipped_empty_text",
    "message",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text.replace("đ", "d")).strip()


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"(?<!\w)(?:\+?84|0)(?:[\s.-]*\d){8,10}(?!\w)", "[PHONE]", text)
    return text


def extract_url_id(url: object) -> str:
    path = urlparse(str(url or "")).path
    match = re.search(r"-(\d+)\.html/?$", path) or re.search(r"/(\d+)\.html/?$", path)
    return match.group(1) if match else ""


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {normalize(c).replace(" ", "_"): c for c in df.columns}
    for candidate in candidates:
        key = normalize(candidate).replace(" ", "_")
        if key in lookup:
            return lookup[key]
    return None


def load_catalog() -> list[dict]:
    for path in (PRODUCTS_FILE, CATEGORIES_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {path}")

    products = pd.read_csv(PRODUCTS_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    categories = pd.read_csv(CATEGORIES_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    p_id = find_column(products, ["product_id", "id"])
    p_name = find_column(products, ["product_name", "name", "title"])
    p_url = find_column(products, ["product_url", "url", "source_url"])
    c_id = find_column(categories, ["product_id", "id", "source_product_id"])
    c_name = find_column(categories, ["category", "category_name", "product_category", "category_label"])
    if not all([p_id, p_name, p_url, c_id, c_name]):
        raise ValueError(
            f"Không tìm được cột catalog cần thiết. products={list(products.columns)}; "
            f"categories={list(categories.columns)}"
        )

    mask = categories[c_name].map(
        lambda x: "sua tam" in normalize(x)
    )
    category_ids = categories.loc[mask, c_id].astype(str).str.strip().drop_duplicates()
    if category_ids.empty:
        raise RuntimeError("Không tìm thấy danh mục sữa tắm trong product_categories.csv")

    catalog = products.loc[
        products[p_id].astype(str).str.strip().isin(set(category_ids))
    ].copy()
    catalog = catalog.rename(
        columns={p_id: "product_id", p_name: "product_name", p_url: "product_url"}
    )
    catalog["product_url"] = catalog["product_url"].astype(str).str.strip()
    catalog = catalog[catalog["product_url"].str.startswith("http", na=False)].copy()
    catalog["original_url_id"] = catalog["product_url"].map(extract_url_id)
    catalog = catalog[catalog["original_url_id"] != ""].drop_duplicates("product_url")

    if catalog.empty:
        raise RuntimeError(
            "Không tìm thấy URL sản phẩm hợp lệ trong danh mục sữa tắm."
        )

    # Mỗi URL catalog có log riêng kể cả khi nhiều URL chuyển về cùng canonical ID.
    # Review vẫn được deduplicate theo (canonical ID, review ID).
    return catalog.to_dict("records")


def resolve_product(session: requests.Session, product_url: str) -> dict:
    response = session.get(product_url, timeout=TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical_url = canonical_tag.get("href", "").strip() if canonical_tag else ""
    if not canonical_url:
        og_url = soup.find("meta", property="og:url")
        canonical_url = og_url.get("content", "").strip() if og_url else ""
    canonical_url = urljoin(product_url, html.unescape(canonical_url)) if canonical_url else product_url

    title_tag = soup.find("meta", property="og:title")
    canonical_name = clean_text(title_tag.get("content", "")) if title_tag else ""
    if not canonical_name and soup.title:
        canonical_name = clean_text(soup.title.get_text(" ", strip=True))

    original_id = extract_url_id(product_url)
    canonical_id = extract_url_id(canonical_url)
    if not canonical_id:
        raise RuntimeError(
            f"Canonical URL không có ID hợp lệ; không gọi API bằng ID đoán. URL={canonical_url}"
        )
    return {
        "original_url_id": original_id,
        "canonical_product_id": canonical_id,
        "canonical_url": canonical_url,
        "canonical_name": canonical_name,
    }


def fetch_json(session: requests.Session, params: dict) -> dict:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(API_URL, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("API không trả JSON object")
            status = payload.get("status", {})
            if not isinstance(status, dict) or status.get("error_code") != 0:
                raise RuntimeError(f"API báo lỗi: {status}")
            if not isinstance(payload.get("data"), dict):
                raise RuntimeError("Response không có data object")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Request thất bại sau {MAX_RETRIES} lần: {last_error}")


def get_total(data: dict):
    if data.get("total") is not None:
        try:
            return int(data["total"])
        except (TypeError, ValueError):
            pass
    rating = data.get("rating", {})
    filters = rating.get("filter", []) if isinstance(rating, dict) else []
    for item in filters:
        if isinstance(item, dict) and item.get("key") == "filter_all":
            try:
                return int(item.get("count", 0))
            except (TypeError, ValueError):
                pass
    return None


def load_existing() -> dict[tuple[str, str], dict]:
    rows = {}
    if not OUTPUT_FILE.exists():
        return rows
    with OUTPUT_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            product_id = str(row.get("source_product_id", "")).strip()
            review_id = str(row.get("review_id", "")).strip()
            source_url = str(row.get("source_url", "")).strip()
            text = clean_text(row.get("review_text", ""))
            # Keep only rows that meet current validation rules.
            if not product_id or not review_id or not text or extract_url_id(source_url) != product_id:
                continue
            row["review_text"] = text
            row.setdefault("original_url_id", "")
            rows[(product_id, review_id)] = {field: row.get(field, "") for field in REVIEW_FIELDS}
    return rows


def save_reviews(rows: dict[tuple[str, str], dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows.values())


def ensure_log_schema() -> None:
    """Move an older-schema test log aside before writing the expanded log."""
    if not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0:
        return
    try:
        with LOG_FILE.open("r", encoding="utf-8-sig", newline="") as f:
            existing_header = next(csv.reader(f), [])
    except Exception:
        existing_header = []
    if existing_header != LOG_FIELDS:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = LOG_FILE.with_name(f"{LOG_FILE.stem}_previous_schema_{stamp}{LOG_FILE.suffix}")
        LOG_FILE.replace(backup)
        print(f"Log cũ khác cấu trúc đã được giữ riêng tại: {backup}")


def append_log(values: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0
    with LOG_FILE.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({field: values.get(field, "") for field in LOG_FIELDS})


def collect_product(session: requests.Session, product: dict,
                    rows: dict[tuple[str, str], dict]) -> dict:
    original_url = str(product.get("product_url", "")).strip()
    catalog_name = clean_text(product.get("product_name", ""))
    resolved = resolve_product(session, original_url)
    original_id = resolved["original_url_id"]
    canonical_id = resolved["canonical_product_id"]
    canonical_url = resolved["canonical_url"]
    canonical_name = resolved["canonical_name"] or catalog_name

    log = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "original_url_id": original_id,
        "canonical_product_id": canonical_id,
        "api_product_id": canonical_id,
        "original_url": original_url,
        "canonical_url": canonical_url,
        "product_name": canonical_name,
        "status": "error",
        "api_total": "",
        "reviews_added": 0,
        "reviews_skipped_product_id_mismatch": 0,
        "reviews_skipped_empty_text": 0,
        "message": "",
    }

    if original_id != str(product.get("original_url_id", "")):
        raise RuntimeError("URL ID thay đổi so với catalog; dừng để kiểm tra.")

    print(f"  Original URL ID={original_id}; canonical/API ID={canonical_id}")
    print(f"  Original URL: {original_url}")
    print(f"  Canonical URL: {canonical_url}")
    print(f"  Canonical title: {canonical_name}")

    total = None
    added = 0
    mismatches = 0
    empty_text = 0
    page = 1
    seen_pages: set[tuple[str, ...]] = set()
    seen_reviews: set[tuple[str, str]] = set()

    while page <= MAX_PAGES:
        params = {
            "product_id": canonical_id,
            "page": page,
            "size": PAGE_SIZE,
            "sort": "create",
            "filter": "filter_all",
            "is_desktop": 1,
        }
        payload = fetch_json(session, params)
        data = payload["data"]
        reviews = data.get("reviews", [])
        if not isinstance(reviews, list):
            raise RuntimeError(f"Trang {page}: data.reviews không phải danh sách")
        if total is None:
            total = get_total(data)
            log["api_total"] = total if total is not None else ""
            print(f"  API total (tham khảo): {total}")
        if not reviews:
            break

        signature = tuple(
            f"{str(item.get('product_id', '')).strip()}:{str(item.get('id', '')).strip()}"
            for item in reviews if isinstance(item, dict)
        )
        if signature in seen_pages:
            log["message"] = f"Dừng vì trang {page} lặp lại danh sách review."
            break
        seen_pages.add(signature)

        for item in reviews:
            if not isinstance(item, dict):
                continue
            review_id = str(item.get("id", "")).strip()
            if not review_id:
                continue
            item_product_id = str(item.get("product_id", "")).strip()
            if not item_product_id or item_product_id != canonical_id:
                mismatches += 1
                continue

            text = clean_text(item.get("content", ""))
            if not text:
                empty_text += 1
                continue

            key = (canonical_id, review_id)
            if key in seen_reviews or key in rows:
                continue
            seen_reviews.add(key)

            rating = item.get("rating") or {}
            created_at = item.get("created_at")
            try:
                review_date = datetime.fromtimestamp(int(created_at)).isoformat(sep=" ") if created_at else ""
            except (ValueError, TypeError, OSError, OverflowError):
                review_date = ""

            rows[key] = {
                "source": "hasaki",
                "category": "Sữa tắm",
                "source_product_id": canonical_id,
                "product_name": canonical_name,
                "review_id": review_id,
                "rating": rating.get("star", "") if isinstance(rating, dict) else "",
                "review_text": text,
                "review_date": review_date,
                "is_bought": item.get("is_bought", ""),
                "has_images": bool(item.get("images") or item.get("data_images")),
                "source_url": canonical_url,
                "original_url_id": original_id,
            }
            added += 1

        print(
            f"  Trang {page}: API trả {len(reviews)}; mới {added}; "
            f"lệch/thiếu ID {mismatches}; rỗng nội dung {empty_text}"
        )
        if len(reviews) < PAGE_SIZE:
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    if page > MAX_PAGES:
        log["message"] = f"Dừng ở giới hạn MAX_PAGES={MAX_PAGES}."

    log["reviews_added"] = added
    log["reviews_skipped_product_id_mismatch"] = mismatches
    log["reviews_skipped_empty_text"] = empty_text
    if mismatches or empty_text:
        log["status"] = "partial"
        if not log["message"]:
            log["message"] = "Đã bỏ qua review thiếu/lệch ID hoặc không có nội dung."
    elif total == 0:
        log["status"] = "no_reviews"
        if not log["message"]:
            log["message"] = "API báo không có review cho sản phẩm này."
    else:
        log["status"] = "success"
        if not log["message"]:
            log["message"] = "Hoàn tất; các review được lưu đã khớp API product_id và có nội dung."
    log["message"] = (
        f"original_url_id={original_id}; canonical_product_id={canonical_id}; "
        f"api_product_id={canonical_id}. {log['message']}"
    )
    return log


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_log_schema()
    catalog = load_catalog()
    print("CHẾ ĐỘ THU THẬP: toàn bộ danh mục Sữa tắm")
    print("Số URL sản phẩm trong catalog:", len(catalog))
    print("CSV:", OUTPUT_FILE)
    print("Log:", LOG_FILE)

    rows = load_existing()
    print("Review hợp lệ đã có sau kiểm tra lại:", len(rows))

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://hasaki.vn/",
    })

    # Log mỗi URL riêng, kể cả khi nhiều URL trỏ về cùng canonical ID.
    # Reviews vẫn dedupe theo canonical ID + review ID.
    for index, product in enumerate(catalog, start=1):
        print(f"\n[{index}/{len(catalog)}] {product.get('product_name', '')} (URL ID {product['original_url_id']})")
        try:
            log = collect_product(session, product, rows)
            save_reviews(rows)
            append_log(log)
            print(
                f"  Kết quả: {log['status']} | thêm {log['reviews_added']} | "
                f"lệch ID {log['reviews_skipped_product_id_mismatch']} | "
                f"rỗng {log['reviews_skipped_empty_text']}"
            )
        except Exception as exc:
            original_url = str(product.get("product_url", "")).strip()
            error_log = {
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "original_url_id": product.get("original_url_id", ""),
                "canonical_product_id": "",
                "api_product_id": "",
                "original_url": original_url,
                "canonical_url": "",
                "product_name": clean_text(product.get("product_name", "")),
                "status": "error",
                "api_total": "",
                "reviews_added": 0,
                "reviews_skipped_product_id_mismatch": 0,
                "reviews_skipped_empty_text": 0,
                "message": f"{type(exc).__name__}: {exc}",
            }
            save_reviews(rows)
            append_log(error_log)
            print("  LỖI:", exc)
        time.sleep(REQUEST_DELAY)

    save_reviews(rows)
    print("\nHoàn tất thu thập danh mục Sữa tắm.")
    print("Tổng review hợp lệ trong file:", len(rows))
    print("CSV:", OUTPUT_FILE)
    print("Log:", LOG_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

 