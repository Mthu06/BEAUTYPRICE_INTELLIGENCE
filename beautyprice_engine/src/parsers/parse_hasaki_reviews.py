
"""
Collect public product reviews from Hasaki for BeautyPrice Intelligence.

Default: test one product (Hasaki product ID 183033).
Optional: use --all-products to collect reviews for products in
data/processed/price_snapshots.csv.

Output:
    data/interim/hasaki/hasaki_reviews.csv

Privacy:
    - Do not save reviewer names or user IDs.
    - Strip HTML from review content.
    - Redact phone numbers and email addresses in review text.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests


# ============================================================
# 1. PROJECT PATHS AND CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SNAPSHOT_FILE = PROJECT_ROOT / "data" / "processed" / "price_snapshots.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "interim" / "hasaki"
OUTPUT_FILE = OUTPUT_DIR / "hasaki_reviews.csv"

API_URL = "https://hasaki.vn/mobile/v3/detail/product/rating-reviews"
PILOT_PRODUCT_ID = "183033"

PAGE_SIZE = 5
REQUEST_TIMEOUT = 25
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

OUTPUT_COLUMNS = [
    "review_id",
    "product_id",
    "review_text",
    "review_rating",
    "review_date",
    "source",
    "collected_at",
]


# ============================================================
# 2. TEXT CLEANING AND PRIVACY
# ============================================================

def clean_review_text(value) -> str:
    """Remove HTML and redact common contact information."""
    if value is None:
        return ""

    text = str(value)

    # Convert common HTML line breaks before removing tags.
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)

    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    # Redact email addresses.
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL REDACTED]",
        text,
    )

    # Redact Vietnamese-style phone numbers, including +84.
    # This is intentionally conservative to avoid replacing
    # short numbers that may be meaningful in a review.
    phone_pattern = (
        r"(?<!\d)(?:\+?84|0)"
        r"(?:[\s.\-()]?\d){8,10}(?!\d)"
    )
    text = re.sub(phone_pattern, "[PHONE REDACTED]", text)

    return text


def parse_review_date(timestamp):
    """Convert Unix timestamp to a Vietnam-local ISO date/time."""
    if timestamp in (None, ""):
        return ""

    try:
        value = float(timestamp)
        if value <= 0:
            return ""

        return datetime.fromtimestamp(
            value, tz=VIETNAM_TZ
        ).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def get_rating(review: dict):
    """Extract the numeric star rating from the API response."""
    rating = review.get("rating")

    if isinstance(rating, dict):
        rating = rating.get("star")

    try:
        value = float(rating)
        if 1 <= value <= 5:
            return value
    except (TypeError, ValueError):
        pass

    return None


# ============================================================
# 3. LOAD PRODUCT URLS
# ============================================================

def extract_product_id(product_url: str):
    """
    Extract the numeric Hasaki product ID from a URL ending
    with a slug such as ...-183033.html.
    """
    if not isinstance(product_url, str):
        return None

    match = re.search(r"-(\d+)\.html(?:[?#].*)?$", product_url)
    return match.group(1) if match else None


def load_products(all_products: bool):
    """
    Return a list of dictionaries:
        {"product_id": "...", "product_url": "..."}
    """
    if not all_products:
        return [{
            "product_id": PILOT_PRODUCT_ID,
            "product_url": (
                "https://hasaki.vn/san-pham/"
                "kem-chong-nang-la-roche-posay-spf-50-"
                "bao-ve-da-50ml-183033.html"
            ),
        }]

    if not SNAPSHOT_FILE.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file snapshot: {SNAPSHOT_FILE}"
        )

    snapshots = pd.read_csv(
        SNAPSHOT_FILE,
        dtype={"product_url": "string"},
    )

    if "product_url" not in snapshots.columns:
        raise ValueError(
            "price_snapshots.csv không có cột product_url."
        )

    products = []

    for url in snapshots["product_url"].dropna().astype(str):
        product_id = extract_product_id(url)

        if product_id:
            products.append({
                "product_id": product_id,
                "product_url": url,
            })

    # One URL per numeric Hasaki product ID.
    unique_products = {}
    for product in products:
        unique_products.setdefault(
            product["product_id"], product
        )

    return list(unique_products.values())


# ============================================================
# 4. REQUEST THE HASAKI REVIEWS API
# ============================================================

def build_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Referer": "https://hasaki.vn/",
    })

    return session


def fetch_reviews_page(
    session: requests.Session,
    product_id: str,
    product_url: str,
    page: int,
):
    """Fetch one page and validate the API response."""
    params = {
        "product_id": product_id,
        "page": page,
        "size": PAGE_SIZE,
        "sort": "create",
        "filter": "filter_all",
        "is_desktop": 1,
    }

    headers = {"Referer": product_url}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                API_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                print(
                    f"  HTTP {response.status_code} | "
                    f"product={product_id} | page={page}"
                )
                print(f"  Request URL: {response.url}")
                print(
                    "  Response preview: "
                    + response.text[:500].replace("\n", " ")
                )

            response.raise_for_status()

            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError(
                    "API không trả về JSON hợp lệ. "
                    f"URL: {response.url}"
                ) from exc

            status = payload.get("status", {})
            error_code = status.get("error_code")

            if error_code not in (None, 0, "0"):
                raise RuntimeError(
                    "Hasaki API báo lỗi: "
                    f"{status.get('error_message', status)}"
                )

            data = payload.get("data", {})
            if not isinstance(data, dict):
                raise ValueError(
                    "Cấu trúc JSON không có data dạng object."
                )

            reviews = data.get("reviews", [])
            if not isinstance(reviews, list):
                raise ValueError(
                    "Trường data.reviews không phải danh sách."
                )

            total = data.get("total", 0)

            try:
                total = int(total or 0)
            except (TypeError, ValueError):
                total = 0

            return reviews, total

        except (
            requests.RequestException,
            ValueError,
            RuntimeError,
        ) as exc:
            print(
                f"  Lần thử {attempt}/{MAX_RETRIES} thất bại: {exc}"
            )

            if attempt == MAX_RETRIES:
                raise

            time.sleep(attempt * 2)

    return [], 0


# ============================================================
# 5. PARSE REVIEWS WITHOUT REVIEWER IDENTIFIERS
# ============================================================

def parse_reviews(
    reviews: list,
    product_id: str,
    collected_at: str,
):
    records = []

    for review in reviews:
        if not isinstance(review, dict):
            continue

        review_id = review.get("id")
        if review_id in (None, ""):
            continue

        text = clean_review_text(review.get("content", ""))

        # Keep only records with actual review text.
        if not text:
            continue

        records.append({
            "review_id": str(review_id),
            "product_id": str(product_id),
            "review_text": text,
            "review_rating": get_rating(review),
            "review_date": parse_review_date(
                review.get("created_at")
            ),
            "source": "Hasaki",
            "collected_at": collected_at,
        })

    return records


# ============================================================
# 6. COLLECT ALL PAGES FOR ONE PRODUCT
# ============================================================

def collect_product(
    session: requests.Session,
    product: dict,
):
    product_id = str(product["product_id"])
    product_url = product["product_url"]

    print(f"\nSản phẩm Hasaki ID: {product_id}")

    all_records = []
    seen_review_ids = set()
    page = 1
    total_reviews = None

    while True:
        print(f"  Đang lấy trang {page}...")

        reviews, reported_total = fetch_reviews_page(
            session=session,
            product_id=product_id,
            product_url=product_url,
            page=page,
        )

        if total_reviews is None:
            total_reviews = reported_total
            print(f"  API báo tổng số đánh giá: {total_reviews}")

        if not reviews:
            print("  Trang không có đánh giá; dừng phân trang.")
            break

        collected_at = datetime.now(VIETNAM_TZ).isoformat(
            timespec="seconds"
        )

        records = parse_reviews(
            reviews=reviews,
            product_id=product_id,
            collected_at=collected_at,
        )

        for record in records:
            review_id = record["review_id"]

            if review_id not in seen_review_ids:
                seen_review_ids.add(review_id)
                all_records.append(record)

        print(
            f"  Nhận {len(reviews)} bản ghi API; "
            f"đã giữ {len(all_records)} đánh giá duy nhất."
        )

        # Stop when the API's reported total is reached.
        if total_reviews and page * PAGE_SIZE >= total_reviews:
            break

        # A short page usually indicates the last page.
        if len(reviews) < PAGE_SIZE:
            break

        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_records


# ============================================================
# 7. SAVE RESULTS SAFELY
# ============================================================

def save_results(new_records: list):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    new_df = pd.DataFrame(new_records, columns=OUTPUT_COLUMNS)

    # Preserve prior results and avoid duplicate review IDs
    # for the same product when the script is run again.
    if OUTPUT_FILE.exists():
        old_df = pd.read_csv(
            OUTPUT_FILE,
            dtype={
                "review_id": "string",
                "product_id": "string",
            },
        )

        for column in OUTPUT_COLUMNS:
            if column not in old_df.columns:
                old_df[column] = pd.NA

        old_df = old_df[OUTPUT_COLUMNS]
        combined = pd.concat(
            [old_df, new_df],
            ignore_index=True,
        )
    else:
        combined = new_df

    if not combined.empty:
        combined["review_id"] = combined["review_id"].astype("string")
        combined["product_id"] = combined["product_id"].astype("string")

        combined = combined.drop_duplicates(
            subset=["product_id", "review_id"],
            keep="last",
        )

    combined.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 60)
    print("HOÀN TẤT THU THẬP ĐÁNH GIÁ")
    print(f"Số bản ghi mới từ lần chạy này: {len(new_df)}")
    print(f"Tổng bản ghi duy nhất trong file: {len(combined)}")
    print(f"File kết quả: {OUTPUT_FILE}")
    print("=" * 60)


# ============================================================
# 8. MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Thu thập đánh giá sản phẩm công khai từ Hasaki."
    )
    parser.add_argument(
        "--all-products",
        action="store_true",
        help=(
            "Thu thập đánh giá cho các sản phẩm có trong "
            "data/processed/price_snapshots.csv. "
            "Mặc định chỉ chạy sản phẩm thử nghiệm 183033."
        ),
    )
    args = parser.parse_args()

    try:
        products = load_products(args.all_products)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Lỗi dữ liệu đầu vào: {exc}")
        sys.exit(1)

    if not products:
        print("Không tìm thấy sản phẩm có product ID hợp lệ.")
        sys.exit(1)

    print(f"Số sản phẩm cần xử lý: {len(products)}")
    print(f"API: {API_URL}")

    session = build_session()
    all_records = []
    failed_products = []

    for index, product in enumerate(products, start=1):
        print(f"\n[{index}/{len(products)}]")

        try:
            records = collect_product(session, product)
            all_records.extend(records)
        except Exception as exc:
            product_id = product["product_id"]
            failed_products.append(product_id)
            print(
                f"Không thu thập được sản phẩm {product_id}: {exc}"
            )

        if index < len(products):
            time.sleep(REQUEST_DELAY_SECONDS)

    save_results(all_records)

    if failed_products:
        print("\nCác sản phẩm bị lỗi:")
        print(", ".join(failed_products))
        print(
            "Bạn có thể chạy lại sau; dữ liệu đã lưu từ những "
            "sản phẩm thành công sẽ được giữ lại."
        )


if __name__ == "__main__":
    main()
