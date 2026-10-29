"""
Collect Guardian sunscreen reviews from Guardian Magento review AJAX pages.

Run from project root:
    python src/collectors/collect_guardian_sunscreen_reviews.py --max-products 3
    python src/collectors/collect_guardian_sunscreen_reviews.py

Inputs:
    data/processed/products.csv
    data/processed/product_categories.csv

Outputs:
    data/interim/guardian/by_category/kem_chong_nang_reviews.csv
    data/interim/guardian/by_category/kem_chong_nang_log.csv

Important:
- Existing review rows are preserved and deduplicated by (Guardian entity ID, review ID).
- Reviewer names/IDs are not stored.
- HTTP 403 / Cloudflare challenge pages are logged as blocked, not as "no reviews".
- This script does not attempt to bypass access controls.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_FILE = ROOT / "data" / "processed" / "products.csv"
CATEGORIES_FILE = ROOT / "data" / "processed" / "product_categories.csv"
OUTPUT_DIR = ROOT / "data" / "interim" / "guardian" / "by_category"
OUTPUT_FILE = OUTPUT_DIR / "kem_chong_nang_reviews.csv"
LOG_FILE = OUTPUT_DIR / "kem_chong_nang_log.csv"

SITE_ROOT = "https://www.guardian.com.vn"
CATEGORY_LABEL = "Chống nắng"
CATEGORY_ALIASES = ("chong nang",)
REQUEST_DELAY = 1.25
TIMEOUT = 30
MAX_RETRIES = 3
MAX_PAGES = 100

REVIEW_FIELDS = [
    "source", "category", "source_product_id", "product_name", "review_id",
    "rating", "review_text", "review_date", "is_bought", "has_images", "source_url",
]
LOG_FIELDS = [
    "time", "category", "product_name", "product_url", "guardian_entity_id",
    "status", "pages_checked", "reviews_seen", "reviews_added", "message",
]


class CloudflareBlockedError(RuntimeError):
    """Raised when Guardian returns an access challenge instead of page content."""


def canonical_guardian_url(value: object) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return url
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "guardian.com.vn":
        return parsed._replace(
            scheme="https", netloc="www.guardian.com.vn"
        ).geturl()
    return url


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text.replace("đ", "d")).strip()


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"(?<!\w)(?:\+?84|0)(?:[\s.-]?\d){8,10}(?!\w)", "[PHONE]", text)
    return text


def find_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    by_normalized = {
        normalize(col).replace(" ", "_"): col for col in df.columns
    }
    for candidate in candidates:
        key = normalize(candidate).replace(" ", "_")
        if key in by_normalized:
            return by_normalized[key]
    return None


def load_catalog() -> list[dict]:
    for path in (PRODUCTS_FILE, CATEGORIES_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy file đầu vào: {path}")

    products = pd.read_csv(PRODUCTS_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    categories = pd.read_csv(CATEGORIES_FILE, dtype=str, encoding="utf-8-sig").fillna("")

    p_id = find_col(products, ("product_id", "id"))
    p_name = find_col(products, ("product_name", "name", "title"))
    p_url = find_col(products, ("product_url", "url", "source_url"))
    p_source = find_col(products, ("source", "retailer", "retailer_name", "retailer_id"))
    c_id = find_col(categories, ("product_id", "id", "source_product_id"))
    c_name = find_col(
        categories, ("category", "category_name", "product_category", "category_label")
    )

    if not all((p_id, p_name, p_url, p_source, c_id, c_name)):
        raise ValueError(
            f"Thiếu cột cần thiết. products.csv={list(products.columns)}; "
            f"product_categories.csv={list(categories.columns)}"
        )

    guardian = products[
        products[p_source].map(lambda value: "guardian" in normalize(value))
    ].copy()
    if guardian.empty:
        raise RuntimeError(f"Không tìm thấy sản phẩm Guardian trong cột '{p_source}'.")

    mask = categories[c_name].map(
        lambda value: any(alias in normalize(value) for alias in CATEGORY_ALIASES)
    )
    links = categories.loc[mask, [c_id, c_name]].copy()
    if links.empty:
        raise RuntimeError(
            f"Không tìm thấy danh mục '{CATEGORY_LABEL}'. Các nhãn hiện có: "
            f"{categories[c_name].value_counts().to_dict()}"
        )

    guardian[p_id] = guardian[p_id].astype(str).str.strip()
    links[c_id] = links[c_id].astype(str).str.strip()
    catalog = guardian.merge(
        links.drop_duplicates(c_id), left_on=p_id, right_on=c_id, how="inner"
    )
    catalog = catalog.rename(columns={p_name: "product_name", p_url: "product_url"})
    catalog["product_url"] = catalog["product_url"].map(canonical_guardian_url)
    catalog = catalog[
        catalog["product_url"].str.startswith(("http://", "https://"), na=False)
    ]
    catalog = catalog[
        catalog["product_url"].str.contains(
            r"https?://(?:www\.)?guardian\.com\.vn/", case=False, regex=True, na=False
        )
    ]
    catalog = catalog.drop_duplicates("product_url")
    if catalog.empty:
        raise RuntimeError(f"Không có URL Guardian hợp lệ trong danh mục '{CATEGORY_LABEL}'.")
    return catalog[["product_name", "product_url"]].to_dict("records")


def is_cloudflare_challenge(response: requests.Response) -> bool:
    body = response.text[:20000].lower()
    return (
        response.status_code == 403
        or "just a moment..." in body
        or "challenges.cloudflare.com" in body
        or "cf-chl-" in body
    )


def request_text(
    session: requests.Session, url: str, params: dict | None = None
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, params=params, timeout=TIMEOUT)
            if is_cloudflare_challenge(response):
                raise CloudflareBlockedError(
                    f"Guardian trả HTTP {response.status_code} hoặc trang Cloudflare challenge "
                    f"tại {response.url}. Không thể xác nhận review bằng request này."
                )
            response.raise_for_status()
            if not response.text.strip():
                raise RuntimeError("Response rỗng")
            return response.text
        except CloudflareBlockedError:
            raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Request thất bại sau {MAX_RETRIES} lần: {last_error}")


def extract_entity_id(product_html: str) -> str:
    patterns = (
        r"/review/product/listAjax/id/(\d+)",
        r"review/product/listAjax/id[\\/'\":\s]+(\d+)",
        r"/review/product/view/id/(\d+)",
        r"/review/product/list/id/(\d+)",
        r'data-product-id=["\'](\d+)["\']',
        r'data-entity-id=["\'](\d+)["\']',
        r'"entity_id"\s*:\s*"?(\d+)"?',
        r'"productId"\s*:\s*"?(\d+)"?',
    )
    for pattern in patterns:
        match = re.search(pattern, product_html, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_product_name(product_html: str, fallback: str) -> str:
    soup = BeautifulSoup(product_html, "html.parser")
    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        return clean_text(meta["content"])
    h1 = soup.find("h1")
    return clean_text(h1.get_text(" ", strip=True)) if h1 else clean_text(fallback)


def parse_reviews(
    review_html: str, entity_id: str, product_name: str, product_url: str
) -> list[dict]:
    soup = BeautifulSoup(review_html, "html.parser")
    review_nodes = soup.select("li.review-item.amreview-review-wrapper[data-amreview-id]")
    parsed: list[dict] = []

    for node in review_nodes:
        review_id = str(node.get("data-amreview-id", "")).strip()
        text_node = node.select_one(
            '.amreview-description [data-amshowmore-js="text"]'
        ) or node.select_one('.amreview-description [itemprop="description"]')
        review_text = clean_text(text_node.get_text(" ", strip=True)) if text_node else ""

        rating: float | str = ""
        rating_node = node.select_one(
            '.rating-result[itemprop="reviewRating"] [itemprop="ratingValue"]'
        )
        if rating_node:
            try:
                raw_rating = float(rating_node.get_text(strip=True))
                rating = round(raw_rating / 20, 2) if raw_rating > 5 else raw_rating
            except (ValueError, TypeError):
                rating = ""

        if rating == "":
            title = node.select_one('.rating-result[itemprop="reviewRating"]')
            match = re.search(r"(\d+(?:\.\d+)?)", title.get("title", "") if title else "")
            if match:
                raw_rating = float(match.group(1))
                rating = round(raw_rating / 20, 2) if raw_rating > 5 else raw_rating

        date_node = node.select_one(".amreview-date time[datetime]")
        review_date = clean_text(date_node.get("datetime", "")) if date_node else ""

        if not review_id:
            stable = f"{entity_id}|{review_date}|{rating}|{review_text}"
            review_id = "hash_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]

        if not (review_text or rating != "" or review_date):
            continue

        parsed.append({
            "source": "guardian",
            "category": CATEGORY_LABEL,
            "source_product_id": entity_id,
            "product_name": product_name,
            "review_id": review_id,
            "rating": rating,
            "review_text": review_text,
            "review_date": review_date,
            "is_bought": "yes" if node.select_one(".amreview-verified") else "",
            "has_images": bool(node.select(
                ".amreview-images a.amreview-image-link[href], .amreview-images img.amreview-image"
            )),
            "source_url": product_url,
        })
    return parsed


def max_page_from_html(review_html: str) -> int:
    soup = BeautifulSoup(review_html, "html.parser")
    max_page = 1
    for link in soup.select(".pages a[href], .pager a[href], a[href]"):
        href = str(link.get("href", ""))
        for raw in parse_qs(urlparse(href).query).get("p", []):
            try:
                max_page = max(max_page, int(raw))
            except ValueError:
                continue
    return min(max_page, MAX_PAGES)


def load_existing() -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    if not OUTPUT_FILE.exists():
        return rows
    with OUTPUT_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            product_id = str(row.get("source_product_id", "")).strip()
            review_id = str(row.get("review_id", "")).strip()
            if product_id and review_id:
                rows[(product_id, review_id)] = {
                    field: row.get(field, "") for field in REVIEW_FIELDS
                }
    return rows


def save_reviews(rows: dict[tuple[str, str], dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows.values())


def preflight_log_writable() -> None:
    """Fail before making network requests if the log is locked/unwritable."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8-sig", newline=""):
            pass
    except PermissionError as exc:
        raise PermissionError(
            f"Không ghi được file log: {LOG_FILE}\n"
            "Hãy đóng file CSV trong Excel/ứng dụng khác rồi chạy lại."
        ) from exc


def append_log(row: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0
    with LOG_FILE.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def collect_one_product(
    session: requests.Session,
    product: dict,
    rows: dict[tuple[str, str], dict],
) -> None:
    url = str(product["product_url"]).strip()
    fallback_name = clean_text(product.get("product_name", ""))
    log = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "category": CATEGORY_LABEL,
        "product_name": fallback_name,
        "product_url": url,
        "guardian_entity_id": "",
        "status": "error",
        "pages_checked": 0,
        "reviews_seen": 0,
        "reviews_added": 0,
        "message": "",
    }

    try:
        product_html = request_text(session, url)
        entity_id = extract_entity_id(product_html)
        log["guardian_entity_id"] = entity_id
        if not entity_id:
            raise RuntimeError(
                "Không tìm thấy review AJAX ID/entity ID trong HTML sản phẩm; "
                "bỏ qua an toàn, không đoán ID."
            )

        product_name = extract_product_name(product_html, fallback_name)
        log["product_name"] = product_name
        ajax_url = urljoin(SITE_ROOT, f"/review/product/listAjax/id/{entity_id}/")

        pages_checked = reviews_seen = added = 0
        seen_signatures: set[str] = set()
        page_no = 1
        max_page = 1

        while page_no <= min(MAX_PAGES, max_page if max_page > 1 else MAX_PAGES):
            params = {"p": page_no} if page_no > 1 else None
            review_html = request_text(session, ajax_url, params=params)
            pages_checked += 1

            soup = BeautifulSoup(review_html, "html.parser")
            signature = hashlib.sha256(
                soup.get_text(" ", strip=True).encode("utf-8")
            ).hexdigest()
            if signature in seen_signatures:
                log["message"] = f"Dừng vì trang {page_no} lặp nội dung."
                break
            seen_signatures.add(signature)

            max_page = max(max_page, max_page_from_html(review_html))
            page_reviews = parse_reviews(review_html, entity_id, product_name, url)
            if not page_reviews:
                # Do not call this "no reviews" if response was a challenge page:
                # request_text() has already raised for known challenge signatures.
                break

            reviews_seen += len(page_reviews)
            for review in page_reviews:
                key = (review["source_product_id"], review["review_id"])
                if key not in rows:
                    rows[key] = review
                    added += 1

            print(
                f"    Trang {page_no}: {len(page_reviews)} review; "
                f"thêm mới tích lũy {added}; trang tối đa phát hiện: {max_page}"
            )
            if page_no >= max_page:
                break
            page_no += 1
            time.sleep(REQUEST_DELAY)

        log.update({
            "status": "success" if reviews_seen else "no_reviews",
            "pages_checked": pages_checked,
            "reviews_seen": reviews_seen,
            "reviews_added": added,
        })
        if not reviews_seen:
            log["message"] = "Phản hồi hợp lệ nhưng không tìm thấy review theo selectors đã xác minh."
        elif not log["message"]:
            log["message"] = "OK"

    except CloudflareBlockedError as exc:
        log["status"] = "blocked"
        log["message"] = str(exc)
    except PermissionError:
        # Let file permission problems stop the run rather than masking them.
        raise
    except Exception as exc:
        log["status"] = "error"
        log["message"] = f"{type(exc).__name__}: {exc}"
    finally:
        # Checkpoint existing + newly collected rows before writing log.
        save_reviews(rows)
        append_log(log)
        print(
            f"  {log['status']} | Guardian ID={log['guardian_entity_id'] or '-'} | "
            f"seen={log['reviews_seen']} | added={log['reviews_added']} | {log['message']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect Guardian sunscreen reviews; preserves existing CSV rows."
    )
    parser.add_argument(
        "--max-products", type=int, default=None,
        help="Giới hạn số sản phẩm để chạy thử; ví dụ --max-products 3",
    )
    args = parser.parse_args()
    if args.max_products is not None and args.max_products < 1:
        parser.error("--max-products phải >= 1")

    try:
        preflight_log_writable()
        catalog = load_catalog()
        if args.max_products is not None:
            catalog = catalog[:args.max_products]
        rows = load_existing()
    except Exception as exc:
        print(f"LỖI KHỞI TẠO: {exc}", file=sys.stderr)
        return 1

    print("GUARDIAN | Review danh mục chống nắng")
    print(f"Sản phẩm trong lượt chạy: {len(catalog)}")
    print(f"Review hiện có (deduplicated): {len(rows)}")
    print(f"CSV: {OUTPUT_FILE}")
    print(f"Log: {LOG_FILE}")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": SITE_ROOT + "/",
    })

    for index, product in enumerate(catalog, start=1):
        print(f"\n[{index}/{len(catalog)}] {product.get('product_name', '')}")
        collect_one_product(session, product, rows)
        time.sleep(REQUEST_DELAY)

    save_reviews(rows)
    print("\nHoàn tất lượt chạy.")
    print(f"Tổng review duy nhất: {len(rows)}")
    print(f"CSV: {OUTPUT_FILE.resolve()}")
    print(f"Log: {LOG_FILE.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

