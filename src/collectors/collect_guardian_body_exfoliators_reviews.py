"""
Guardian body-exfoliator review collector using Selenium (no requests).

Run from project root:
    python src/collectors/collect_guardian_body_exfoliators_reviews.py --max-products 1 --max-pages-per-product 3

Inputs:
    data/processed/products.csv
    data/processed/product_categories.csv

Outputs:
    data/interim/guardian/by_category/tay_te_bao_chet_reviews.csv
    data/interim/guardian/by_category/tay_te_bao_chet_log.csv

Behavior:
- Uses a normal Chrome browser controlled by Selenium.
- Does not use requests or the unverified `limit=10` parameter.
- Uses the observed pagination parameter `p`.
- Preserves existing CSV rows and deduplicates by (Guardian entity ID, review ID).
- Recognizes a confirmed empty review list as `no_reviews`.
- Uses the observed pagination links and the optional per-product page limit.
- If the main CSV is locked, writes a recovery CSV instead of aborting the run.
- If Guardian shows a Cloudflare challenge, logs it as blocked and does not bypass it.
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
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_FILE = ROOT / "data" / "processed" / "products.csv"
CATEGORIES_FILE = ROOT / "data" / "processed" / "product_categories.csv"
OUTPUT_DIR = ROOT / "data" / "interim" / "guardian" / "by_category"
OUTPUT_FILE = OUTPUT_DIR / "tay_te_bao_chet_reviews.csv"
RECOVERY_FILE = OUTPUT_DIR / "tay_te_bao_chet_reviews_recovery.csv"
LOG_FILE = OUTPUT_DIR / "tay_te_bao_chet_log.csv"

SITE_ROOT = "https://www.guardian.com.vn"
CATEGORY_LABEL = "Tẩy tế bào chết cơ thể"
CATEGORY_ALIASES = (
    "tay te bao chet co the", "tay te bao chet body"
)
PAGE_LOAD_TIMEOUT = 45
WAIT_AFTER_NAVIGATION = 2.0
PAGE_DELAY = 2.0
# Recreate Chrome periodically during long pagination runs to reduce renderer/session crashes.
RESTART_DRIVER_EVERY_PAGES = 10
MAX_PAGES = 100

REVIEW_FIELDS = [
    "source", "category", "source_product_id", "product_name", "review_id",
    "rating", "review_text", "review_date", "is_bought", "has_images",
    "source_url",
]
LOG_FIELDS = [
    "time", "category", "product_name", "product_url", "guardian_entity_id",
    "status", "pages_checked", "reviews_seen", "reviews_added", "message",
]


class CloudflareBlockedError(RuntimeError):
    """Guardian returned a challenge/interstitial instead of review content."""


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    # Avoid retaining direct contact details in review text.
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

    products = pd.read_csv(
        PRODUCTS_FILE, dtype=str, encoding="utf-8-sig"
    ).fillna("")
    categories = pd.read_csv(
        CATEGORIES_FILE, dtype=str, encoding="utf-8-sig"
    ).fillna("")

    p_id = find_col(products, ("product_id", "id"))
    p_name = find_col(products, ("product_name", "name", "title"))
    p_url = find_col(products, ("product_url", "url", "source_url"))
    p_source = find_col(
        products, ("source", "retailer", "retailer_name", "retailer_id")
    )
    c_id = find_col(categories, ("product_id", "id", "source_product_id"))
    c_name = find_col(
        categories,
        ("category", "category_name", "product_category", "category_label"),
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
        raise RuntimeError(
            f"Không tìm thấy sản phẩm Guardian trong cột '{p_source}'."
        )

    normalized_aliases = {normalize(alias) for alias in CATEGORY_ALIASES}
    mask = categories[c_name].map(
        lambda value: normalize(value) in normalized_aliases
    )
    links = categories.loc[mask, [c_id, c_name]].copy()
    if links.empty:
        raise RuntimeError(
            f"Không tìm thấy danh mục '{CATEGORY_LABEL}'. "
            f"Nhãn hiện có: {categories[c_name].value_counts().to_dict()}"
        )

    guardian[p_id] = guardian[p_id].astype(str).str.strip()
    links[c_id] = links[c_id].astype(str).str.strip()
    catalog = guardian.merge(
        links.drop_duplicates(c_id), left_on=p_id, right_on=c_id, how="inner"
    )
    catalog = catalog.rename(
        columns={p_name: "product_name", p_url: "product_url"}
    )
    catalog["product_url"] = catalog["product_url"].astype(str).str.strip()
    catalog = catalog[
        catalog["product_url"].str.contains(
            r"https?://(?:www\.)?guardian\.com\.vn/",
            case=False, regex=True, na=False,
        )
    ].drop_duplicates("product_url")

    if catalog.empty:
        raise RuntimeError(
            f"Không có URL Guardian hợp lệ trong danh mục '{CATEGORY_LABEL}'."
        )

    return catalog[["product_name", "product_url"]].to_dict("records")


def make_driver(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1365,950")
    options.add_argument("--lang=vi-VN")
    # Do not add stealth, proxy rotation, or challenge-bypass settings.
    driver = webdriver.Chrome(service=Service(), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


def is_challenge_page(page_html: str, page_title: str) -> bool:
    body = (page_html or "")[:30000].lower()
    title = (page_title or "").lower()
    return (
        "just a moment" in title
        or "just a moment..." in body
        or "challenges.cloudflare.com" in body
        or "cf-chl-" in body
        or "verify you are human" in body
    )


def navigate_and_get_html(driver: webdriver.Chrome, url: str) -> tuple[str, str]:
    try:
        driver.get(url)
    except TimeoutException:
        # A timed-out navigation can still have a usable DOM; inspect it below.
        pass
    time.sleep(WAIT_AFTER_NAVIGATION)
    page_html = driver.page_source or ""
    current_url = driver.current_url
    title = driver.title or ""

    if is_challenge_page(page_html, title):
        raise CloudflareBlockedError(
            f"Chrome hiển thị trang xác minh/challenge tại {current_url}. "
            "Dừng thu thập và không tự động vượt qua challenge."
        )

    if not page_html.strip():
        raise RuntimeError(f"Chrome không nhận được HTML tại {current_url}")

    return page_html, current_url


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
    nodes = soup.select(
        "li.review-item.amreview-review-wrapper[data-amreview-id]"
    )
    parsed = []

    for node in nodes:
        review_id = str(node.get("data-amreview-id", "")).strip()
        text_node = (
            node.select_one('.amreview-description [data-amshowmore-js="text"]')
            or node.select_one('.amreview-description [itemprop="description"]')
        )
        review_text = (
            clean_text(text_node.get_text(" ", strip=True)) if text_node else ""
        )

        rating: float | str = ""
        rating_node = node.select_one(
            '.rating-result[itemprop="reviewRating"] [itemprop="ratingValue"]'
        )
        if rating_node:
            try:
                raw = float(rating_node.get_text(strip=True))
                rating = round(raw / 20, 2) if raw > 5 else raw
            except (ValueError, TypeError):
                rating = ""

        if rating == "":
            outer = node.select_one('.rating-result[itemprop="reviewRating"]')
            match = re.search(r"(\d+(?:\.\d+)?)", outer.get("title", "") if outer else "")
            if match:
                raw = float(match.group(1))
                rating = round(raw / 20, 2) if raw > 5 else raw

        date_node = node.select_one(".amreview-date time[datetime]")
        review_date = clean_text(date_node.get("datetime", "")) if date_node else ""

        if not review_id:
            stable = f"{entity_id}|{review_date}|{rating}|{review_text}"
            review_id = "hash_" + hashlib.sha256(
                stable.encode("utf-8")
            ).hexdigest()[:20]

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
                ".amreview-images a[href], .amreview-images img"
            )),
            "source_url": product_url,
        })
    return parsed



def confirms_no_reviews(review_html: str) -> bool:
    """Return True only when Guardian explicitly renders an empty review state."""
    soup = BeautifulSoup(review_html, "html.parser")
    text = normalize(soup.get_text(" ", strip=True))
    if not any(phrase in text for phrase in (
        "chua co danh gia", "there are no reviews", "no reviews yet",
        "be the first to review this product",
    )):
        return False

    # If actual review nodes exist, do not classify the page as empty.
    return not bool(soup.select(
        "li.review-item.amreview-review-wrapper[data-amreview-id]"
    ))

def max_page_from_html(review_html: str) -> int:
    soup = BeautifulSoup(review_html, "html.parser")
    max_page = 1
    for link in soup.select(".pages a[href], .pager a[href]"):
        href = str(link.get("href", ""))
        for value in parse_qs(urlparse(href).query).get("p", []):
            try:
                max_page = max(max_page, int(value))
            except ValueError:
                pass
    return min(max_page, MAX_PAGES)


def load_existing() -> dict[tuple[str, str], dict]:
    """Load both the main output and any recovery output, deduplicating across them."""
    existing = {}
    for path in (OUTPUT_FILE, RECOVERY_FILE):
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                key = (
                    str(row.get("source_product_id", "")).strip(),
                    str(row.get("review_id", "")).strip(),
                )
                if all(key):
                    existing[key] = {
                        field: row.get(field, "") for field in REVIEW_FIELDS
                    }
    return existing


def save_reviews(rows: dict[tuple[str, str], dict]) -> Path:
    """Save all deduplicated rows; use a recovery file if the main CSV is locked."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def write_to(path: Path) -> None:
        temp_path = path.with_name(path.stem + ".tmp" + path.suffix)
        with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=REVIEW_FIELDS)
            writer.writeheader()
            writer.writerows(rows.values())
        temp_path.replace(path)

    try:
        write_to(OUTPUT_FILE)
        return OUTPUT_FILE
    except PermissionError:
        # Excel or another program may be holding the main CSV open.
        # Keep the existing file untouched and save the latest combined data separately.
        write_to(RECOVERY_FILE)
        print(
            f"  CẢNH BÁO: Không ghi được CSV chính (có thể đang mở). "
            f"Đã lưu bản phục hồi tại: {RECOVERY_FILE}"
        )
        return RECOVERY_FILE


def preflight_log_writable() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8-sig", newline=""):
            pass
    except PermissionError as exc:
        raise PermissionError(
            f"Không ghi được file log: {LOG_FILE}. "
            "Hãy đóng file log trong Excel hoặc ứng dụng khác."
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
    driver: webdriver.Chrome,
    product: dict,
    rows: dict[tuple[str, str], dict],
    max_pages_per_product: int | None,
) -> webdriver.Chrome:
    product_url = str(product["product_url"]).strip()
    fallback_name = clean_text(product.get("product_name", ""))
    log = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "category": CATEGORY_LABEL,
        "product_name": fallback_name,
        "product_url": product_url,
        "guardian_entity_id": "",
        "status": "error",
        "pages_checked": 0,
        "reviews_seen": 0,
        "reviews_added": 0,
        "message": "",
    }

    try:
        product_html, _ = navigate_and_get_html(driver, product_url)
        entity_id = extract_entity_id(product_html)
        log["guardian_entity_id"] = entity_id
        if not entity_id:
            raise RuntimeError(
                "Không tìm thấy review AJAX ID trong HTML sản phẩm; "
                "không tự đoán ID."
            )

        product_name = extract_product_name(product_html, fallback_name)
        log["product_name"] = product_name
        ajax_url = urljoin(
            SITE_ROOT, f"/review/product/listAjax/id/{entity_id}/"
        )

        pages_checked = reviews_seen = added = 0
        seen_page_hashes = set()
        page_no = 1

        while page_no <= MAX_PAGES:
            # Direct navigation in Chrome; no requests library and no limit=10.
            page_url = ajax_url if page_no == 1 else f"{ajax_url}?p={page_no}"
            review_html, actual_url = navigate_and_get_html(driver, page_url)
            pages_checked += 1

            soup = BeautifulSoup(review_html, "html.parser")
            page_hash = hashlib.sha256(
                soup.get_text(" ", strip=True).encode("utf-8")
            ).hexdigest()
            if page_hash in seen_page_hashes:
                log["message"] = f"Dừng vì trang {page_no} lặp nội dung."
                break
            seen_page_hashes.add(page_hash)

            page_reviews = parse_reviews(
                review_html, entity_id, product_name, product_url
            )






            if not page_reviews:
                if confirms_no_reviews(review_html):
                    log["status"] = "no_reviews"
                    log["message"] = (
                        f"Guardian xác nhận sản phẩm chưa có đánh giá "
                        f"ở trang {page_no}."
                    )
                else:
                    log["status"] = "parse_mismatch"
                    log["message"] = (
                        f"Không tìm thấy review và HTML cũng không xác nhận "
                        f"trạng thái rỗng ở trang {page_no}. "
                        f"Chrome URL={actual_url}; cần kiểm tra HTML debug."
                    )
                break

            reviews_seen += len(page_reviews)
            for review in page_reviews:
                key = (review["source_product_id"], review["review_id"])
                if key not in rows:
                    rows[key] = review
                    added += 1

            detected_last_page = max_page_from_html(review_html)
            print(
                f"    Trang {page_no}: {len(page_reviews)} review; "
                f"tối đa trang trong pager hiện thấy: {detected_last_page}"
            )

            if (
                max_pages_per_product is not None
                and pages_checked >= max_pages_per_product
            ):
                log["message"] = (
                    f"Dừng theo giới hạn thử nghiệm "
                    f"{max_pages_per_product} trang/sản phẩm."
                )
                break

            if page_no >= detected_last_page:
                break

            page_no += 1
            time.sleep(PAGE_DELAY)

            # Long review pagination can disconnect Chrome's renderer.
            # Restart the browser periodically, then continue with the next page.
            if pages_checked % RESTART_DRIVER_EVERY_PAGES == 0:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = make_driver()
                print(
                    f"    Đã khởi động lại Chrome sau {pages_checked} trang; "
                    f"tiếp tục từ trang {page_no}."
                )

        if reviews_seen:
            log["status"] = "success"
        elif log["status"] not in ("no_reviews", "parse_mismatch"):
            log["status"] = "no_reviews"
        log.update({
            "pages_checked": pages_checked,
            "reviews_seen": reviews_seen,
            "reviews_added": added,
        })
        if not log["message"]:
            log["message"] = "OK"

    except CloudflareBlockedError as exc:
        log["status"] = "blocked"
        log["message"] = str(exc)
    except Exception as exc:
        log["status"] = "error"
        log["message"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            save_reviews(rows)
        except Exception as save_exc:
            # Do not crash the entire multi-product run because one save failed.
            log["message"] = (
                (log["message"] + " | ") if log["message"] else ""
            ) + f"Không lưu được CSV: {type(save_exc).__name__}: {save_exc}"
            print(f"  CẢNH BÁO LƯU CSV: {save_exc}")
        try:
            append_log(log)
        except Exception as log_exc:
            print(f"  CẢNH BÁO LƯU LOG: {log_exc}")
        print(
            f"  {log['status']} | Guardian ID={log['guardian_entity_id'] or '-'} | "
            f"seen={log['reviews_seen']} | added={log['reviews_added']} | "
            f"{log['message']}"
        )

    return driver


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect Guardian body-exfoliator reviews with Selenium Chrome."
    )
    parser.add_argument("--max-products", type=int, default=None)
    parser.add_argument("--max-pages-per-product", type=int, default=None)
    parser.add_argument(
        "--headless", action="store_true",
        help="Chạy Chrome headless; mặc định mở cửa sổ Chrome để dễ quan sát.",
    )
    args = parser.parse_args()

    if args.max_products is not None and args.max_products < 1:
        parser.error("--max-products phải >= 1")
    if args.max_pages_per_product is not None and args.max_pages_per_product < 1:
        parser.error("--max-pages-per-product phải >= 1")

    try:
        preflight_log_writable()
        catalog = load_catalog()
        if args.max_products is not None:
            catalog = catalog[:args.max_products]
        rows = load_existing()
    except Exception as exc:
        print(f"LỖI KHỞI TẠO: {exc}", file=sys.stderr)
        return 1

    print("GUARDIAN | Review danh mục Tẩy tế bào chết cơ thể | Selenium")
    print(f"Sản phẩm trong lượt chạy: {len(catalog)}")
    print(f"Review hiện có (deduplicated): {len(rows)}")
    print(f"CSV: {OUTPUT_FILE}")
    print(f"Log: {LOG_FILE}")

    driver = None
    try:
        driver = make_driver(headless=args.headless)
        for index, product in enumerate(catalog, start=1):
            print(f"\n[{index}/{len(catalog)}] {product.get('product_name', '')}")
            driver = collect_one_product(
                driver,
                product,
                rows,
                max_pages_per_product=args.max_pages_per_product,
            )
            # If a session died while collecting this product, recover before
            # moving to the next one. The failed product remains in the log.
            try:
                _ = driver.current_url
            except WebDriverException:
                print("  Chrome mất phiên; đang tạo phiên mới cho sản phẩm tiếp theo...")
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = make_driver(headless=args.headless)
            time.sleep(PAGE_DELAY)
    except WebDriverException as exc:
        print(
            "LỖI SELENIUM/CHROME: "
            f"{exc}\nKiểm tra Chrome đã cài và Selenium Manager có thể "
            "khởi tạo ChromeDriver hay không.",
            file=sys.stderr,
        )
        return 1
    finally:
        if driver is not None:
            driver.quit()

    try:
        saved_path = save_reviews(rows)
        print(f"\nĐã lưu dữ liệu cuối lượt chạy: {saved_path.resolve()}")
    except Exception as exc:
        print(f"\nCẢNH BÁO: Không lưu được CSV cuối lượt chạy: {exc}", file=sys.stderr)
    print("Hoàn tất lượt chạy.")
    print(f"Tổng review duy nhất: {len(rows)}")
    print(f"CSV: {OUTPUT_FILE.resolve()}")
    print(f"Log: {LOG_FILE.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

