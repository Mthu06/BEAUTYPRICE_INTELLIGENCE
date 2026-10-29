
"""
Thegioiskinfood facial cleanser review collector.
Uses Selenium and rendered browser HTML; does not call the review API.
"""

import argparse
import csv
import hashlib
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# =========================================================
# 1. CONFIGURATION
# =========================================================

BASE_URL = "https://thegioiskinfood.com"
CATEGORY_URL = (
    "https://thegioiskinfood.com/collections/sua-rua-mat?page={page}"
)

WAIT_SECONDS = 20
DELAY_SECONDS = 1
HEADLESS = False

MAX_CATEGORY_ATTEMPTS = 3
MAX_REVIEW_LOAD_ATTEMPTS = 3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = (
    PROJECT_ROOT / "data" / "interim"
    / "thegioiskinfood" / "by_category"
)
OUTPUT_FILE = OUTPUT_DIR / "facewash_reviews.csv"
LOG_FILE = OUTPUT_DIR / "collect_facewash_reviews.log"
PRODUCT_LOG_FILE = OUTPUT_DIR / "collect_facewash_reviews_log.csv"
DIAGNOSTIC_FILE = OUTPUT_DIR / "review_diagnostic_facewash.html"

PRODUCT_CARD_SELECTOR = ".proLoop.relative.changeimage"
PRODUCT_LINK_SELECTORS = (
    "a.productImgLink",
    "p.productName a",
)

# Review selectors based on the HTML supplied in this conversation.
REVIEW_ITEM_SELECTOR = (
    ".hrv-crv-rating__ritem, .hrv-crv-ritem"
)
REVIEW_ID_SELECTOR = ".hrv-crv-ritem__actions[data-rating-id]"
REVIEW_CONTENT_SELECTOR = ".hrv-crv-ritem__content"
REVIEW_STARS_SELECTOR = (
    ".hrv-crv-ritem__body .hrv-crv-rating__star-groups svg"
)

CSV_FIELDS = [
    "source",
    "category",
    "product_name",
    "product_url",
    "product_id",
    "reviewer_name",
    "review_id",
    "rating",
    "review_date",
    "review_content",
    "has_text",
    "review_key",
]

PRODUCT_LOG_FIELDS = [
    "time",
    "source",
    "category",
    "product_name",
    "product_url",
    "source_product_id",
    "status",
    "pages_checked",
    "reviews_seen",
    "reviews_added",
    "message",
]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# =========================================================
# 2. SELENIUM HELPERS
# =========================================================

def create_driver():
    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"

    if HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1440,1000")
    options.add_argument("--lang=vi-VN")
    options.add_argument("--disable-notifications")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(35)
    return driver


def pause(seconds=None):
    time.sleep(DELAY_SECONDS if seconds is None else seconds)


def safe_text(element):
    try:
        return " ".join((element.text or "").split()).strip()
    except (StaleElementReferenceException, WebDriverException):
        return ""


def safe_attribute(element, name):
    try:
        return (element.get_attribute(name) or "").strip()
    except (StaleElementReferenceException, WebDriverException):
        return ""


def append_product_log(row):
    new_file = (
        not PRODUCT_LOG_FILE.exists()
        or PRODUCT_LOG_FILE.stat().st_size == 0
    )

    with PRODUCT_LOG_FILE.open(
        "a", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=PRODUCT_LOG_FIELDS,
            extrasaction="ignore",
        )
        if new_file:
            writer.writeheader()
        writer.writerow(row)


# =========================================================
# 3. PRODUCT DISCOVERY
# =========================================================

def extract_product_link(card):
    for selector in PRODUCT_LINK_SELECTORS:
        try:
            for link in card.find_elements(By.CSS_SELECTOR, selector):
                href = safe_attribute(link, "href")
                if not href:
                    continue

                url = urljoin(BASE_URL, href)
                parsed = urlparse(url)

                if (
                    parsed.netloc.endswith("thegioiskinfood.com")
                    and "/products/" in parsed.path
                ):
                    name = safe_text(link)
                    if not name:
                        name = safe_attribute(link, "title")
                    return url, name

        except WebDriverException:
            continue

    return "", ""


def extract_category_product_id(card):
    try:
        elements = card.find_elements(
            By.CSS_SELECTOR, "[data-product-id]"
        )
        for element in elements:
            value = safe_attribute(element, "data-product-id")
            if value:
                return value
    except WebDriverException:
        pass

    return ""


def collect_products(driver, category_pages):
    """
    Read every requested category page.
    Deduplicate products by URL before applying start/end positions.
    """
    products_by_url = {}

    for page_number in range(1, category_pages + 1):
        category_url = CATEGORY_URL.format(page=page_number)
        logger.info(
            "Category page %s/%s: %s",
            page_number, category_pages, category_url,
        )

        cards = []

        for attempt in range(1, MAX_CATEGORY_ATTEMPTS + 1):
            try:
                driver.get(category_url)

                WebDriverWait(driver, WAIT_SECONDS).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR)
                    )
                )

                pause()
                cards = driver.find_elements(
                    By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR
                )

                if cards:
                    break

            except (TimeoutException, WebDriverException) as exc:
                logger.warning(
                    "Category attempt %s/%s failed: %s",
                    attempt,
                    MAX_CATEGORY_ATTEMPTS,
                    str(exc).splitlines()[0],
                )
                if attempt < MAX_CATEGORY_ATTEMPTS:
                    pause(attempt * 2)

        if not cards:
            logger.warning(
                "No product cards found on category page %s",
                page_number,
            )
            continue

        logger.info("Cards found on category page: %s", len(cards))

        for card in cards:
            try:
                url, name = extract_product_link(card)
                if not url:
                    continue

                if url not in products_by_url:
                    products_by_url[url] = {
                        "product_name": name,
                        "product_url": url,
                        "product_id": extract_category_product_id(card),
                    }

            except StaleElementReferenceException:
                continue

    products = list(products_by_url.values())
    logger.info("Unique products discovered: %s", len(products))
    return products


# =========================================================
# 4. PRODUCT METADATA AND REVIEW WIDGET
# =========================================================

def get_product_metadata(driver, product):
    metadata = dict(product)

    for selector in ("h1", ".product-title", ".productName"):
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                title = safe_text(element)
                if title:
                    metadata["product_name"] = title
                    break
            if metadata.get("product_name"):
                break
        except WebDriverException:
            continue

    # Prefer the product ID on the detail page's review widget.
    try:
        widgets = driver.find_elements(
            By.CSS_SELECTOR, ".hrv-crv-container[data-product-id]"
        )
        for widget in widgets:
            value = safe_attribute(widget, "data-product-id")
            if value and widget.is_displayed():
                metadata["product_id"] = value
                break
    except WebDriverException:
        pass

    logger.info(
        "Product ID: %s",
        metadata.get("product_id") or "UNKNOWN",
    )
    return metadata


def activate_review_section(driver):
    """Scroll to the review area and attempt to activate a review tab."""
    visited = False

    for selector in (
        ".page-product-info-reviews",
        ".hrv-crv-container",
        "#reviews",
        "[id*='review']",
    ):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                if element.is_displayed():
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});",
                        element,
                    )
                    pause(1)
                    visited = True
                    break
            if visited:
                break
        except WebDriverException:
            continue

    # Click only controls whose visible label or attributes suggest reviews.
    for selector in (
        "a[href*='review']",
        "[href='#reviews']",
        "[data-target*='review']",
        "[data-bs-target*='review']",
    ):
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                if not element.is_displayed():
                    continue

                label = " ".join([
                    safe_text(element),
                    safe_attribute(element, "href"),
                    safe_attribute(element, "class"),
                ]).lower()

                if not any(
                    word in label
                    for word in ("review", "rating", "đánh giá", "danh-gia")
                ):
                    continue

                try:
                    driver.execute_script("arguments[0].click();", element)
                    pause(1)
                    visited = True
                    break
                except WebDriverException:
                    continue

            if visited:
                break
        except WebDriverException:
            continue

    pause(2)
    return visited


# =========================================================
# 5. REVIEW CARD DETECTION
# =========================================================

def find_review_items(driver):
    """
    Identify cards using data-rating-id.
    Do not require the reviewer name, date, or text to exist.
    """
    results = []
    seen = set()

    try:
        elements = driver.find_elements(
            By.CSS_SELECTOR, REVIEW_ITEM_SELECTOR
        )

        for item in elements:
            try:
                if not item.is_displayed():
                    continue

                id_elements = item.find_elements(
                    By.CSS_SELECTOR, REVIEW_ID_SELECTOR
                )
                review_id = (
                    safe_attribute(id_elements[0], "data-rating-id")
                    if id_elements else ""
                )

                if review_id and review_id not in seen:
                    seen.add(review_id)
                    results.append(item)

            except (StaleElementReferenceException, WebDriverException):
                continue

    except WebDriverException as exc:
        logger.warning("Review-card scan failed: %s", exc)

    return results


def extract_reviewer_name(item):
    selectors = (
        ".hrv-crv-ritem-header__name",
        ".hrv-crv-ritem__name",
        ".hrv-crv-rating__name",
        "[class*='reviewer-name']",
        "[class*='customer-name']",
    )

    for selector in selectors:
        try:
            for element in item.find_elements(By.CSS_SELECTOR, selector):
                value = safe_text(element)
                if value:
                    return value
        except WebDriverException:
            continue

    return ""


def extract_review_date(item):
    selectors = (
        ".hrv-crv-ritem-header__date",
        ".hrv-crv-ritem__date",
        ".hrv-crv-rating__date",
        "time",
        "[class*='review-date']",
        "[class*='rating-date']",
    )

    for selector in selectors:
        try:
            for element in item.find_elements(By.CSS_SELECTOR, selector):
                value = (
                    safe_text(element)
                    or safe_attribute(element, "datetime")
                )
                if value:
                    return value
        except WebDriverException:
            continue

    return ""


def extract_review_content(item):
    try:
        elements = item.find_elements(
            By.CSS_SELECTOR, REVIEW_CONTENT_SELECTOR
        )
        if elements:
            return safe_text(elements[0])
    except WebDriverException:
        pass

    return ""


def extract_rating(item):
    """Count filled gold stars in the rendered SVG markup."""
    try:
        stars = item.find_elements(
            By.CSS_SELECTOR, REVIEW_STARS_SELECTOR
        )
        filled = 0

        for star in stars:
            paths = star.find_elements(By.CSS_SELECTOR, "path")
            star_is_filled = False

            for path in paths:
                fill = safe_attribute(path, "fill").lower()
                style = safe_attribute(path, "style").lower()

                if (
                    "#f3c63f" in fill
                    or "#f3c63f" in style
                    or "243, 198, 63" in fill
                ):
                    star_is_filled = True
                    break

            if star_is_filled:
                filled += 1

        if stars:
            return filled

    except WebDriverException:
        pass

    # Fallback for markup exposing a numeric rating.
    for selector in (
        "[data-rating]",
        "[aria-label*='sao']",
        "[aria-label*='star']",
    ):
        try:
            for element in item.find_elements(By.CSS_SELECTOR, selector):
                value = (
                    safe_attribute(element, "data-rating")
                    or safe_attribute(element, "aria-label")
                )
                match = re.search(
                    r"(?<!\d)(10(?:\.0)?|[0-9](?:\.\d+)?)",
                    value,
                )
                if match:
                    number = float(match.group(1))
                    if 0 <= number <= 10:
                        return number
        except WebDriverException:
            continue

    return ""


def extract_review_record(item, product):
    """Build one CSV record from a rendered review card."""
    try:
        id_elements = item.find_elements(
            By.CSS_SELECTOR, REVIEW_ID_SELECTOR
        )
        review_id = (
            safe_attribute(id_elements[0], "data-rating-id")
            if id_elements else ""
        )

        if not review_id:
            return None

        product_id = str(product.get("product_id") or "")
        key_text = f"thegioiskinfood|{product_id}|{review_id}"
        review_key = hashlib.sha256(
            key_text.encode("utf-8")
        ).hexdigest()[:24]

        content = extract_review_content(item)

        return {
            "source": "thegioiskinfood",
            "category": "face_wash",
            "product_name": product.get("product_name", ""),
            "product_url": product.get("product_url", ""),
            "product_id": product_id,
            "reviewer_name": extract_reviewer_name(item),
            "review_id": review_id,
            "rating": extract_rating(item),
            "review_date": extract_review_date(item),
            "review_content": content,
            "has_text": bool(content),
            "review_key": review_key,
        }

    except (StaleElementReferenceException, WebDriverException):
        return None


# =========================================================
# 6. REVIEW PAGINATION
# =========================================================

def review_signature(driver):
    """Unique IDs currently visible in the review widget."""
    ids = []

    for item in find_review_items(driver):
        try:
            elements = item.find_elements(
                By.CSS_SELECTOR, REVIEW_ID_SELECTOR
            )
            review_id = (
                safe_attribute(elements[0], "data-rating-id")
                if elements else ""
            )
            if review_id:
                ids.append(review_id)
        except WebDriverException:
            continue

    return tuple(ids)


def click_review_pagination(driver, previous_signature):
    """
    Try common next-page controls.
    Return True only if the visible review IDs actually change.
    """
    selectors = (
        ".hrv-crv-pagination .next",
        ".hrv-crv-pagination [aria-label*='next']",
        ".hrv-crv-pagination [aria-label*='Next']",
        ".hrv-crv-pagination a",
        ".hrv-crv-pagination button",
        "[class*='pagination'] [class*='next']",
        "[class*='pagination'] a",
        "[class*='pagination'] button",
    )

    candidates = []
    seen = set()

    for selector in selectors:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                try:
                    if not element.is_displayed():
                        continue

                    label = " ".join([
                        safe_text(element),
                        safe_attribute(element, "aria-label"),
                        safe_attribute(element, "title"),
                        safe_attribute(element, "class"),
                        safe_attribute(element, "rel"),
                    ]).lower()

                    if not any(
                        word in label
                        for word in (
                            "next", "tiếp", "sau", "›", "»",
                            "chevron-right", "arrow-right",
                        )
                    ):
                        continue

                    if element.id not in seen:
                        seen.add(element.id)
                        candidates.append(element)

                except WebDriverException:
                    continue
        except WebDriverException:
            continue

    for element in candidates:
        try:
            classes = safe_attribute(element, "class").lower()
            disabled = safe_attribute(element, "aria-disabled").lower()

            if "disabled" in classes or disabled == "true":
                continue

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                element,
            )
            pause(0.5)

            try:
                element.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", element)

            try:
                WebDriverWait(driver, WAIT_SECONDS).until(
                    lambda d: (
                        bool(review_signature(d))
                        and review_signature(d) != previous_signature
                    )
                )
                return True
            except TimeoutException:
                logger.info(
                    "Clicked pagination control but review IDs did not change."
                )

        except (StaleElementReferenceException, WebDriverException):
            continue

    return False


# =========================================================
# 7. CSV OUTPUT
# =========================================================

def load_existing_keys():
    existing = set()

    if not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0:
        return existing

    try:
        with OUTPUT_FILE.open(
            "r", encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file)
            for row in reader:
                key = (row.get("review_key") or "").strip()
                if key:
                    existing.add(key)
    except (OSError, csv.Error) as exc:
        logger.warning("Could not read existing review CSV: %s", exc)

    return existing


def save_reviews(records):
    """Append new reviews without overwriting previously collected data."""
    if not records:
        logger.info("No review records to save for this product.")
        return 0

    existing = load_existing_keys()
    new_records = [
        row for row in records
        if row.get("review_key")
        and row["review_key"] not in existing
    ]

    if not new_records:
        logger.info("No new reviews; all collected IDs already exist.")
        return 0

    file_exists = (
        OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0
    )

    with OUTPUT_FILE.open(
        "a", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
        )
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_records)

    logger.info(
        "Saved %s new review records to %s",
        len(new_records),
        OUTPUT_FILE,
    )
    return len(new_records)


# =========================================================
# 8. COLLECT REVIEWS FOR ONE PRODUCT
# =========================================================

def collect_product_reviews(driver, product, max_review_pages):
    url = product["product_url"]
    logger.info("Opening product: %s", url)

    driver.get(url)
    WebDriverWait(driver, WAIT_SECONDS).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    pause(2)

    product = get_product_metadata(driver, product)
    activate_review_section(driver)

    items_ready = False

    for attempt in range(1, MAX_REVIEW_LOAD_ATTEMPTS + 1):
        try:
            WebDriverWait(driver, WAIT_SECONDS).until(
                lambda d: len(find_review_items(d)) > 0
            )
            items_ready = True
            break

        except TimeoutException:
            logger.warning(
                "Review cards not detected for %s; attempt %s/%s",
                url, attempt, MAX_REVIEW_LOAD_ATTEMPTS,
            )

            try:
                activate_review_section(driver)
                driver.execute_script("window.scrollBy(0, 500);")
            except WebDriverException:
                pass

            pause(attempt * 2)

    if not items_ready:
        logger.warning(
            "No review cards with data-rating-id detected: %s", url
        )

        # Save rendered HTML to help diagnose selectors and loading.
        try:
            DIAGNOSTIC_FILE.write_text(
                driver.page_source, encoding="utf-8"
            )
            logger.info("Diagnostic HTML saved to %s", DIAGNOSTIC_FILE)
        except OSError as exc:
            logger.warning("Could not save diagnostic HTML: %s", exc)

        # The widget might be empty or might not have loaded.
        # Do not treat this as proof that the product has zero reviews.
        return [], 0, "no_reviews_or_widget_unavailable"

    all_records = {}
    pages_checked = 0
    previous_signature = None

    for page_number in range(1, max_review_pages + 1):
        items = find_review_items(driver)
        page_records = []

        for item in items:
            record = extract_review_record(item, product)
            if record:
                page_records.append(record)
                all_records[record["review_key"]] = record

        signature = tuple(
            row["review_id"] for row in page_records
        )
        pages_checked = page_number

        logger.info(
            "Product review page %s: cards=%s, valid=%s, "
            "unique collected=%s",
            page_number,
            len(items),
            len(page_records),
            len(all_records),
        )

        if page_number >= max_review_pages:
            logger.info("Reached the configured review-page limit.")
            break

        if previous_signature is not None and signature == previous_signature:
            logger.info("Review page unchanged; stopping pagination.")
            break

        previous_signature = signature

        if not signature:
            logger.info("No usable review IDs on this page; stopping.")
            break

        if not click_review_pagination(driver, signature):
            logger.info(
                "Next review page not confirmed; stopping this product."
            )
            break

        pause(1)

    records = list(all_records.values())
    status = "success" if records else "no_reviews_or_widget_unavailable"
    return records, pages_checked, status


# =========================================================
# 9. MAIN: SELECT A PRODUCT RANGE
# =========================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Collect Thegioiskinfood facial cleanser reviews with Selenium."
        )
    )

    parser.add_argument(
        "--category-pages",
        type=int,
        default=3,
        help="Number of category pages to inspect.",
    )
    parser.add_argument(
        "--start-product",
        type=int,
        default=1,
        help="1-based starting product position in the deduplicated list.",
    )
    parser.add_argument(
        "--end-product",
        type=int,
        default=100,
        help="1-based ending product position, inclusive.",
    )
    parser.add_argument(
        "--max-review-pages",
        type=int,
        default=100,
        help="Maximum review pages to try per product.",
    )

    args = parser.parse_args()

    if args.category_pages < 1:
        parser.error("--category-pages must be >= 1")
    if args.start_product < 1:
        parser.error("--start-product must be >= 1")
    if args.end_product < args.start_product:
        parser.error("--end-product must be >= --start-product")
    if args.max_review_pages < 1:
        parser.error("--max-review-pages must be >= 1")

    driver = None

    try:
        # Check log writability before opening Chrome.
        try:
            with PRODUCT_LOG_FILE.open(
                "a", encoding="utf-8-sig", newline=""
            ):
                pass
        except PermissionError as exc:
            raise RuntimeError(
                "Cannot write product log. Close it in Excel and retry."
            ) from exc

        driver = create_driver()

        # Discover the full list first; range positions are applied afterward.
        all_products = collect_products(
            driver,
            category_pages=args.category_pages,
        )

        if not all_products:
            logger.error(
                "No products found. Check category pages and selectors."
            )
            return

        total_products = len(all_products)

        if args.start_product > total_products:
            logger.error(
                "Start position %s exceeds discovered product count %s.",
                args.start_product, total_products,
            )
            return

        # end-product is inclusive: 80–100 means 21 positions.
        selected_products = all_products[
            args.start_product - 1 : min(args.end_product, total_products)
        ]

        logger.info(
            "Discovered %s unique products; processing positions %s–%s "
            "(%s products selected).",
            total_products,
            args.start_product,
            min(args.end_product, total_products),
            len(selected_products),
        )

        total_saved = 0

        for position, product in enumerate(
            selected_products,
            start=args.start_product,
        ):
            started_at = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
            product_name = product.get("product_name", "")
            product_url = product.get("product_url", "")
            product_id = product.get("product_id", "")

            logger.info("-" * 60)
            logger.info(
                "Product position %s/%s: %s",
                position, total_products, product_name,
            )

            records = []
            saved = 0
            pages_checked = 0
            status = "error"
            message = ""

            try:
                records, pages_checked, status = collect_product_reviews(
                    driver,
                    product,
                    max_review_pages=args.max_review_pages,
                )

                saved = save_reviews(records)
                total_saved += saved

                if status == "success":
                    message = (
                        f"Collected {len(records)} unique review records."
                    )
                else:
                    message = (
                        "No review cards were detected. The widget may "
                        "be empty or may not have loaded; inspect the log "
                        "and diagnostic HTML."
                    )

            except (
                TimeoutException,
                WebDriverException,
                RuntimeError,
            ) as exc:
                status = "error"
                message = f"{type(exc).__name__}: {exc}"
                logger.exception("Failed product: %s", product_url)

            finally:
                try:
                    append_product_log({
                        "time": started_at,
                        "source": "thegioiskinfood",
                        "category": "face_wash",
                        "product_name": product_name,
                        "product_url": product_url,
                        "source_product_id": product_id,
                        "status": status,
                        "pages_checked": pages_checked,
                        "reviews_seen": len(records),
                        "reviews_added": saved,
                        "message": message,
                    })
                except (OSError, csv.Error) as exc:
                    logger.warning("Could not append product log: %s", exc)

            logger.info(
                "Result: position=%s, status=%s, collected=%s, saved=%s",
                position, status, len(records), saved,
            )

        logger.info("=" * 60)
        logger.info("RUN FINISHED")
        logger.info("Products discovered: %s", total_products)
        logger.info("Products processed: %s", len(selected_products))
        logger.info("New reviews saved this run: %s", total_saved)
        logger.info("Review CSV: %s", OUTPUT_FILE)
        logger.info("Product log: %s", PRODUCT_LOG_FILE)

    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass


if __name__ == "__main__":
    main()

