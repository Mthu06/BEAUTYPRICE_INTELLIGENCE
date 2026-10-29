
"""
Collect sunscreen product reviews from Thegioiskinfood using Selenium.

Workflow:
1. Open sunscreen category pages.
2. Extract product URLs and names.
3. Open each product page.
4. Read reviews rendered in the browser.
5. Try review pagination / load-more controls.
6. Save review records to CSV.

Note:
- Uses the browser UI; does not call the review API directly.
- Run a small pilot first.
- Website HTML and pagination controls may change.
"""

import argparse
import csv
import hashlib
import logging
import re
import sys
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
    "https://thegioiskinfood.com/collections/kem-chong-nang?page={page}"
)

# Category page count observed from the supplied HTML.
CATEGORY_PAGE_COUNT = 3

# Multi-product collection settings.
# Process the full discovered sunscreen catalog by default (currently 127 products).
# Each product is capped at 40 review pages.
MAX_PRODUCTS = 127
MAX_REVIEW_PAGES_PER_PRODUCT = 40
MAX_PRODUCT_RECOVERY_ATTEMPTS = 2

# False enables category discovery instead of restricting the run to Caryophy.
USE_CARYOPHY_TEST_PRODUCT = False
CARYOPHY_TEST_PRODUCT = {
    "product_name": "Kem Chống Nắng Caryophy Smart Sunscreen 50ml",
    "product_url": "https://thegioiskinfood.com/products/caryophy-smart-sunscreen-50ml",
    "product_id": "1033690058",
}

WAIT_SECONDS = 25  # Wait longer for asynchronous review widgets
DELAY_SECONDS = 0.5  # Short pause between actions; dynamic waits handle loading
HEADLESS = False

# Keep output inside the existing project.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "thegioiskinfood"
    / "by_category"
)
OUTPUT_FILE = OUTPUT_DIR / "sunscreen_reviews.csv"
LOG_FILE = OUTPUT_DIR / "collect_sunscreen_reviews.log"
PRODUCT_LOG_FILE = OUTPUT_DIR / "collect_sunscreen_reviews_log.csv"

# Guardian-style per-product run log. One row is appended per product attempt.
PRODUCT_LOG_FIELDS = [
    "time", "source", "category", "product_name", "product_url",
    "source_product_id", "status", "pages_checked", "reviews_seen",
    "reviews_added", "message",
]
CURRENT_PRODUCT_STATS = {"pages_checked": 0, "reviews_seen": 0}

# Review selectors from the HTML supplied by the user.
REVIEW_ITEM_SELECTOR = ".hrv-crv-rating__ritem"
REVIEW_NAME_SELECTOR = ".hrv-crv-ritem-header__name"
REVIEW_DATE_SELECTOR = ".hrv-crv-ritem-header__date"
REVIEW_CONTENT_SELECTOR = ".hrv-crv-ritem__content"

# Product card selectors from the category page HTML.
PRODUCT_CARD_SELECTOR = ".proLoop.relative.changeimage"
PRODUCT_LINK_SELECTORS = (
    "a.productImgLink",
    "p.productName a",
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


# =========================================================
# 2. LOGGING
# =========================================================

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
# 3. SELENIUM SETUP
# =========================================================

def create_driver():
    """Create a Chrome WebDriver."""
    options = webdriver.ChromeOptions()
    # Do not wait for every third-party asset; the review widget loads asynchronously.
    options.page_load_strategy = "eager"

    if HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1440,1000")
    options.add_argument("--lang=vi-VN")
    options.add_argument("--disable-notifications")

    # Selenium Manager can manage the driver in recent Selenium versions.
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(25)

    return driver


class ProductNavigationError(RuntimeError):
    """Raised when a product page cannot be opened after internal retries."""


def restart_driver(driver):
    """Best-effort restart for a Chrome session that stopped responding."""
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
    time.sleep(2)
    new_driver = create_driver()
    logger.warning("Chrome WebDriver restarted for recovery.")
    return new_driver


def wait_for_page(driver):
    """Wait until the document is ready."""
    WebDriverWait(driver, WAIT_SECONDS).until(
        lambda d: d.execute_script(
            "return document.readyState"
        ) == "complete"
    )


def safe_text(element):
    """Return normalized visible text."""
    try:
        return " ".join(element.text.split()).strip()
    except StaleElementReferenceException:
        return ""


def safe_attribute(element, attribute):
    try:
        return (element.get_attribute(attribute) or "").strip()
    except StaleElementReferenceException:
        return ""


def pause():
    """Small delay between page actions."""
    time.sleep(DELAY_SECONDS)


def preflight_product_log_writable():
    """Check that the per-product CSV log can be written before browsing."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with PRODUCT_LOG_FILE.open("a", encoding="utf-8-sig", newline=""):
            pass
    except PermissionError as exc:
        raise PermissionError(
            f"Không ghi được file log: {PRODUCT_LOG_FILE}. "
            "Hãy đóng file log trong Excel rồi chạy lại."
        ) from exc


def append_product_log(row):
    """Append a Guardian-style product-level audit row."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not PRODUCT_LOG_FILE.exists() or PRODUCT_LOG_FILE.stat().st_size == 0
    with PRODUCT_LOG_FILE.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=PRODUCT_LOG_FIELDS, extrasaction="ignore"
        )
        if new_file:
            writer.writeheader()
        writer.writerow(row)


# =========================================================
# 4. PRODUCT DISCOVERY
# =========================================================

def extract_product_id(card):
    """
    Read data-product-id from the product card.

    The ID is not necessarily the same as a URL variant ID.
    """
    selectors = [
        ".hrv-crv-container",
        "[data-product-id]",
    ]

    for selector in selectors:
        try:
            elements = card.find_elements(By.CSS_SELECTOR, selector)

            for element in elements:
                product_id = safe_attribute(
                    element, "data-product-id"
                )
                if product_id:
                    return product_id
        except WebDriverException:
            continue

    return ""


def extract_product_link(card):
    """Find a product detail link inside a category card."""
    for selector in PRODUCT_LINK_SELECTORS:
        try:
            links = card.find_elements(By.CSS_SELECTOR, selector)

            for link in links:
                href = safe_attribute(link, "href")

                if not href:
                    continue

                absolute_url = urljoin(BASE_URL, href)
                parsed = urlparse(absolute_url)

                if (
                    parsed.netloc.endswith("thegioiskinfood.com")
                    and "/products/" in parsed.path
                ):
                    name = safe_text(link)

                    if not name:
                        name = safe_attribute(link, "title")

                    return absolute_url, name
        except WebDriverException:
            continue

    return "", ""


def collect_products(driver):
    """
    Collect product URLs from the sunscreen category pages.

    Product URLs are deduplicated before opening detail pages.
    """
    products_by_url = {}

    for page_number in range(1, CATEGORY_PAGE_COUNT + 1):
        category_url = CATEGORY_URL.format(page=page_number)

        logger.info(
            "Opening category page %s/%s: %s",
            page_number,
            CATEGORY_PAGE_COUNT,
            category_url,
        )

        cards = []
        for category_attempt in range(1, 3):
            try:
                driver.get(category_url)
                # Eager navigation can return before third-party widgets finish;
                # explicitly wait for the category's product cards.
                WebDriverWait(driver, WAIT_SECONDS).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR)
                    )
                )
                pause()
                cards = driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR)
                if cards:
                    break
                logger.warning(
                    "Category page %s returned no cards on attempt %s/2",
                    page_number, category_attempt,
                )
            except (TimeoutException, WebDriverException) as exc:
                logger.warning(
                    "Category page %s attempt %s/2 failed: %s",
                    page_number, category_attempt, str(exc).splitlines()[0],
                )
                if category_attempt < 2:
                    time.sleep(2 * category_attempt)

        if not cards:
            logger.warning(
                "Skipping category page after 2 attempts: %s",
                category_url,
            )
            continue

        logger.info("Found %s product cards", len(cards))

        for card in cards:
            try:
                product_url, product_name = extract_product_link(card)

                if not product_url:
                    continue

                product_id = extract_product_id(card)

                if product_url not in products_by_url:
                    products_by_url[product_url] = {
                        "product_name": product_name,
                        "product_url": product_url,
                        "product_id": product_id,
                    }

            except StaleElementReferenceException:
                continue

    products = list(products_by_url.values())

    logger.info(
        "Unique sunscreen products discovered: %s",
        len(products),
    )

    # Pilot limit: do not accidentally crawl every product.
    if MAX_PRODUCTS is not None:
        products = products[:MAX_PRODUCTS]

    logger.info("Products selected for this run: %s", len(products))
    return products


# =========================================================
# 5. PRODUCT PAGE METADATA
# =========================================================

def get_product_metadata(driver, product):
    """Read the product title and the ID attached to the actual review widget."""
    metadata = dict(product)

    # Prefer the product's main heading; avoid generic category/card titles.
    for selector in ["h1", ".product-title", ".productName"]:
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

    # The review widget's data-product-id is the useful source ID. Do not
    # take the first arbitrary [data-product-id], which may belong to a card.
    try:
        review_items = driver.find_elements(By.CSS_SELECTOR, REVIEW_ITEM_SELECTOR)
        for item in review_items:
            try:
                actions = item.find_elements(
                    By.CSS_SELECTOR, ".hrv-crv-ritem__actions[data-rating-id]"
                )
                if not actions:
                    continue
                widget_id = driver.execute_script(
                    "const el = arguments[0]; "
                    "const w = el.closest('.hrv-crv-container[data-product-id]'); "
                    "return w ? w.getAttribute('data-product-id') : '';",
                    item,
                )
                if widget_id:
                    metadata["product_id"] = widget_id.strip()
                    return metadata
            except (StaleElementReferenceException, WebDriverException):
                continue

        # If no review is rendered yet, choose a widget that actually contains
        # the review-count label, rather than a product-card widget.
        widgets = driver.find_elements(
            By.CSS_SELECTOR, ".hrv-crv-container[data-product-id]"
        )
        for widget in widgets:
            try:
                text = safe_text(widget).lower()
                product_id = safe_attribute(widget, "data-product-id")
                if product_id and ("đánh giá" in text or "review" in text):
                    metadata["product_id"] = product_id
                    break
            except StaleElementReferenceException:
                continue
    except WebDriverException as exc:
        logger.warning("Could not read review widget metadata: %s", exc)

    return metadata


# =========================================================
# 6. REVIEW EXTRACTION
# =========================================================

def find_review_items(driver):
    """Return only genuine review cards, not empty widget placeholders."""
    valid_items = []
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, REVIEW_ITEM_SELECTOR)
        for item in elements:
            try:
                has_name = bool(item.find_elements(By.CSS_SELECTOR, REVIEW_NAME_SELECTOR))
                has_date = bool(item.find_elements(By.CSS_SELECTOR, REVIEW_DATE_SELECTOR))
                has_id = bool(item.find_elements(
                    By.CSS_SELECTOR, ".hrv-crv-ritem__actions[data-rating-id]"
                ))
                if has_name and has_date and has_id:
                    valid_items.append(item)
            except StaleElementReferenceException:
                continue
    except WebDriverException as exc:
        logger.warning("Cannot read review items: %s", exc)
    return valid_items


def extract_rating(review_element):
    """The supplied review markup represents each star with an SVG."""
    try:
        groups = review_element.find_elements(
            By.CSS_SELECTOR, ".hrv-crv-rating__star-groups"
        )
        for group in groups:
            stars = group.find_elements(By.CSS_SELECTOR, "svg")
            if stars:
                return len(stars)
    except (StaleElementReferenceException, WebDriverException):
        pass

    # Fallback for a future markup variation with a numeric rating.
    for selector in ["[data-rating]", "[aria-label*='sao']", "[aria-label*='star']"]:
        try:
            for element in review_element.find_elements(By.CSS_SELECTOR, selector):
                value = safe_attribute(element, "data-rating") or safe_attribute(element, "aria-label")
                match = re.search(r"(?<!\d)(10(?:\.0)?|[0-9](?:\.\d+)?)", value)
                if match:
                    rating = float(match.group(1))
                    if 0 <= rating <= 10:
                        return rating
        except WebDriverException:
            continue
    return ""


def extract_review_record(review_element, product):
    """Extract a review, preserving rating-only reviews with empty text."""
    try:
        def get_text(selector):
            elements = review_element.find_elements(By.CSS_SELECTOR, selector)
            return safe_text(elements[0]) if elements else ""

        reviewer_name = get_text(REVIEW_NAME_SELECTOR)
        review_date = get_text(REVIEW_DATE_SELECTOR)

        review_content = ""
        for element in review_element.find_elements(By.CSS_SELECTOR, REVIEW_CONTENT_SELECTOR):
            text = safe_text(element)
            if text:
                review_content = text
                break

        rating = extract_rating(review_element)
        actions = review_element.find_elements(
            By.CSS_SELECTOR, ".hrv-crv-ritem__actions[data-rating-id]"
        )
        review_id = safe_attribute(actions[0], "data-rating-id") if actions else ""

        # A real review needs its identifying fields and an ID; empty text is
        # allowed because some customers submit a rating without a comment.
        if not (reviewer_name and review_date and review_id):
            return None

        product_id = product.get("product_id", "")
        key_source = f"thegioiskinfood|{product_id}|{review_id}"
        review_key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:24]

        return {
            "source": "thegioiskinfood",
            "category": "sunscreen",
            "product_name": product.get("product_name", ""),
            "product_url": product.get("product_url", ""),
            "product_id": product_id,
            "reviewer_name": reviewer_name,
            "review_id": review_id,
            "rating": rating,
            "review_date": review_date,
            "review_content": review_content,
            "has_text": bool(review_content),
            "review_key": review_key,
        }
    except (StaleElementReferenceException, WebDriverException):
        return None


# =========================================================
# 7. REVIEW PAGINATION
# =========================================================

def _review_signature(driver):
    """Build a signature from currently rendered review IDs."""
    signature = []
    for item in find_review_items(driver):
        try:
            actions = item.find_elements(
                By.CSS_SELECTOR, ".hrv-crv-ritem__actions[data-rating-id]"
            )
            review_id = safe_attribute(actions[0], "data-rating-id") if actions else ""
            if review_id:
                signature.append(review_id)
        except (StaleElementReferenceException, WebDriverException):
            continue
    return tuple(signature)


def _review_scope_candidates(driver):
    """
    Find the review widget and a few ancestors. Some widgets place pagination
    beside, rather than inside, the review container.
    """
    scopes = []
    items = find_review_items(driver)

    if items:
        try:
            ancestors = driver.execute_script(
                """
                const result = [];
                let node = arguments[0];
                for (let i = 0; node && i < 6; i++, node = node.parentElement) {
                    result.push(node);
                }
                return result;
                """,
                items[0],
            )
            scopes.extend(ancestors or [])
        except WebDriverException:
            pass

    if not scopes:
        scopes.extend(driver.find_elements(
            By.CSS_SELECTOR, ".hrv-crv-container[data-product-id]"
        ))

    # Remove duplicate Selenium elements by their remote element IDs.
    unique = []
    seen = set()
    for scope in scopes:
        try:
            element_id = scope.id
            if element_id not in seen:
                seen.add(element_id)
                unique.append(scope)
        except WebDriverException:
            continue
    return unique


def _pagination_label(element):
    """Collect useful visible and accessibility labels for a control."""
    parts = [
        safe_text(element),
        safe_attribute(element, "aria-label"),
        safe_attribute(element, "title"),
        safe_attribute(element, "class"),
        safe_attribute(element, "rel"),
        safe_attribute(element, "data-page"),
    ]
    try:
        parts.append(element.get_attribute("outerHTML") or "")
    except WebDriverException:
        pass
    return " ".join(parts).lower()


def _control_looks_disabled(driver, element):
    """Detect common disabled states on the custom DIV pagination control."""
    try:
        state = driver.execute_script(
            """
            const el = arguments[0];
            const parent = el.parentElement;
            const cls = (el.className || '').toString().toLowerCase();
            const parentCls = parent
                ? (parent.className || '').toString().toLowerCase()
                : '';
            const ariaDisabled = (el.getAttribute('aria-disabled') || '').toLowerCase();
            const dataPage = (el.getAttribute('data-page') || '').toLowerCase();
            const style = window.getComputedStyle(el);
            return {
                cls,
                parentCls,
                ariaDisabled,
                dataPage,
                pointerEvents: style.pointerEvents,
                opacity: style.opacity,
                disabled: Boolean(el.disabled)
            };
            """,
            element,
        )
        cls = state.get("cls", "")
        parent_cls = state.get("parentCls", "")
        aria_disabled = state.get("ariaDisabled", "")
        pointer_events = state.get("pointerEvents", "")
        disabled_words = ("disabled", "is-disabled", "disable")
        return (
            state.get("disabled", False)
            or aria_disabled == "true"
            or any(word in cls for word in disabled_words)
            or any(word in parent_cls for word in disabled_words)
            or pointer_events == "none"
        )
    except (StaleElementReferenceException, WebDriverException):
        return False


def click_review_pagination(driver):
    """
    Advance the Thegioiskinfood review widget.

    The inspected HTML exposes a custom DIV control named
    .hrv-crv-pagination-next (not a normal button/link). Try this exact
    selector first, then fall back to generic review-specific controls.
    """
    # Exact selector confirmed from the user's DevTools HTML. The pagination
    # is not necessarily inside .hrv-crv-container, so search the whole DOM.
    before = _review_signature(driver)
    exact_selectors = [
        ".hrv-crv-rating__pagination .hrv-crv-pagination-next",
        ".hrv-crv-pagination-next",
    ]
    exact_seen = set()
    for selector in exact_selectors:
        try:
            controls = driver.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            continue
        for control in controls:
            try:
                if control.id in exact_seen:
                    continue
                exact_seen.add(control.id)
                if not control.is_displayed():
                    continue
                cls = safe_attribute(control, "class").lower()
                if _control_looks_disabled(driver, control):
                    logger.info(
                        "Review next control is disabled; likely reached the last page. class=%s",
                        cls,
                    )
                    return False

                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", control
                )
                # Avoid a fixed delay here; wait for the review IDs to change below.
                # This widget uses a DIV with an SVG, so JavaScript click is a
                # useful fallback if Selenium's normal click does not trigger it.
                try:
                    control.click()
                except (ElementClickInterceptedException, WebDriverException):
                    driver.execute_script("arguments[0].click();", control)

                try:
                    WebDriverWait(driver, 4).until(
                        lambda d: bool(_review_signature(d))
                        and _review_signature(d) != before
                    )
                    logger.info(
                        "Advanced review pagination with exact selector: %s",
                        selector,
                    )
                    return True
                except TimeoutException:
                    # Try the next matching exact element/selector; some pages
                    # may contain hidden duplicate widgets.
                    logger.warning(
                        "Clicked %s but review IDs did not change; checking other matching controls.",
                        selector,
                    )
            except (StaleElementReferenceException, WebDriverException) as exc:
                logger.debug("Exact pagination click failed for %s: %s", selector, exc)

    # If the exact widget control exists but clicking it never changes the
    # review IDs, stop safely instead of trying unrelated buttons elsewhere.
    if exact_seen:
        logger.info(
            "Exact review next control was found but did not advance the list; "
            "stopping pagination safely (last page or click did not advance)."
        )
        return False

    scopes = _review_scope_candidates(driver)
    if not scopes:
        logger.warning("Cannot identify a review widget scope for pagination.")
        return False

    selectors = [
        "[rel='next']",
        "button[aria-label*='next' i]",
        "a[aria-label*='next' i]",
        "button[aria-label*='tiếp' i]",
        "a[aria-label*='tiếp' i]",
        "button[class*='next' i]",
        "a[class*='next' i]",
        "button[class*='load-more' i]",
        "a[class*='load-more' i]",
        "button[class*='loadmore' i]",
        "a[class*='loadmore' i]",
        "button[class*='pagination' i]",
        "a[class*='pagination' i]",
        "[role='button'][aria-label*='next' i]",
        "[role='button'][aria-label*='tiếp' i]",
    ]
    candidates = []
    seen = set()

    for scope in scopes:
        for selector in selectors:
            try:
                for element in scope.find_elements(By.CSS_SELECTOR, selector):
                    if element.id not in seen:
                        seen.add(element.id)
                        candidates.append(element)
            except (StaleElementReferenceException, WebDriverException):
                continue

        # Inspect links/buttons in the review area and its nearby ancestors.
        try:
            controls = scope.find_elements(
                By.CSS_SELECTOR, "button, a, [role='button']"
            )
            for element in controls:
                if element.id not in seen:
                    seen.add(element.id)
                    candidates.append(element)
        except (StaleElementReferenceException, WebDriverException):
            continue

    positive_terms = (
        "next", "tiếp", "xem thêm", "xem tiếp", "load more",
        "load-more", "loadmore", "pagination", "page-next",
        "arrow-right", "chevron-right", "sau",
    )
    negative_terms = (
        "previous", "prev", "trước", "back", "đầu", "first",
        "đóng", "close", "share", "report",
    )

    ranked = []
    for element in candidates:
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            label = _pagination_label(element)
            if any(term in label for term in negative_terms):
                continue

            # Numeric page links are considered only if they are within the
            # review widget/ancestor area and not obviously disabled/current.
            text = safe_text(element).strip()
            is_numeric_page = bool(re.fullmatch(r"\d+", text))
            looks_like_next = any(term in label for term in positive_terms)
            if not (looks_like_next or is_numeric_page):
                continue

            class_text = safe_attribute(element, "class").lower()
            aria_current = safe_attribute(element, "aria-current").lower()
            if "disabled" in class_text or aria_current == "page":
                continue

            # Prefer explicit next/load-more controls over numeric page links.
            score = 2 if looks_like_next else 1
            ranked.append((score, element, label[:240]))
        except (StaleElementReferenceException, WebDriverException):
            continue

    ranked.sort(key=lambda item: item[0], reverse=True)

    if not ranked:
        # Log nearby controls so the next iteration can use the site's exact
        # selector rather than guessing.
        diagnostic = []
        for scope in scopes[:3]:
            try:
                for element in scope.find_elements(
                    By.CSS_SELECTOR, "button, a, [role='button']"
                ):
                    if not element.is_displayed():
                        continue
                    label = _pagination_label(element)
                    if label and label not in diagnostic:
                        diagnostic.append(label[:240])
                    if len(diagnostic) >= 15:
                        break
            except WebDriverException:
                continue
            if len(diagnostic) >= 15:
                break
        logger.warning(
            "No review pagination control matched. Visible nearby controls: %s",
            " || ".join(diagnostic) if diagnostic else "(none found)",
        )
        return False

    before = _review_signature(driver)
    for _, control, label in ranked:
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", control
            )
            pause()
            try:
                control.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", control)

            # Wait for review IDs to change. If this candidate was not the
            # correct control, try another candidate rather than claiming
            # pagination succeeded.
            try:
                WebDriverWait(driver, 3.5).until(
                    lambda d: (
                        bool(_review_signature(d))
                        and _review_signature(d) != before
                    )
                )
                logger.info("Review pagination control clicked: %s", label)
                return True
            except TimeoutException:
                logger.info(
                    "Control did not change rendered reviews; trying another."
                )
        except (StaleElementReferenceException, WebDriverException) as exc:
            logger.debug("Could not click pagination candidate: %s", exc)
            continue

    logger.warning(
        "Pagination-like controls were found, but none changed the review list."
    )
    return False


def activate_review_section(driver):
    """
    Activate and wait for the visible customer-review widget.

    The review app is rendered asynchronously. Prefer scrolling to its own
    container and waiting for the supplied review-card selector instead of
    clicking every link whose URL happens to contain "review".
    """
    def visible_review_count():
        """Count real review cards, not empty skeleton/placeholder nodes."""
        try:
            return len(find_review_items(driver))
        except WebDriverException:
            return 0

    def dom_diagnostic():
        """Return compact counts for the live review DOM without collecting review data."""
        try:
            return driver.execute_script("""
                const cards = [...document.querySelectorAll('.hrv-crv-rating__ritem')];
                return {
                  raw_cards: cards.length,
                  cards_with_name: cards.filter(c => (c.querySelector('.hrv-crv-ritem-header__name')?.innerText || '').trim()).length,
                  cards_with_date: cards.filter(c => (c.querySelector('.hrv-crv-ritem-header__date')?.innerText || '').trim()).length,
                  cards_with_review_id: cards.filter(c => !!c.querySelector('.hrv-crv-ritem__actions[data-rating-id]')).length,
                  cards_with_content: cards.filter(c => (c.querySelector('.hrv-crv-ritem__content')?.innerText || '').trim()).length,
                  rating_ids_in_dom: document.querySelectorAll('.hrv-crv-ritem__actions[data-rating-id]').length,
                  image_ids_in_dom: document.querySelectorAll('.hrv-crv-ritem__img-preview-item[data-rating-id]').length,
                  widget_count: document.querySelectorAll('.hrv-crv-container').length
                };
            """)
        except WebDriverException:
            return {}

    # First, bring the actual review widget into view. Some pages have many
    # unrelated widgets/cards with data-product-id, so do not click those.
    try:
        containers = driver.find_elements(
            By.CSS_SELECTOR, ".hrv-crv-container"
        )
        if containers:
            # Prefer the container that already contains review cards; otherwise
            # use the first visible review-widget container.
            target = None
            for container in containers:
                try:
                    if container.find_elements(By.CSS_SELECTOR, REVIEW_ITEM_SELECTOR):
                        target = container
                        break
                    if target is None and container.is_displayed():
                        target = container
                except (StaleElementReferenceException, WebDriverException):
                    continue

            if target is not None:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", target
                )
                # Widget data may be requested after it enters the viewport.
                try:
                    WebDriverWait(driver, 12).until(
                        lambda d: visible_review_count() > 0
                    )
                    logger.info("Review cards appeared after scrolling to review widget.")
                    return True
                except TimeoutException:
                    pass
    except WebDriverException as exc:
        logger.debug("Could not target review widget container: %s", exc)

    # If a dedicated review tab exists, click only controls whose visible label
    # clearly refers to customer reviews (not arbitrary links with review URLs).
    tab_selectors = [
        "[role='tab']", "button", "a", "[role='button']",
        ".product-tab", ".tab-link", ".tab-title",
    ]
    for selector in tab_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            continue

        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                visible_text = safe_text(element).casefold()
                aria = safe_attribute(element, "aria-label").casefold()
                classes = safe_attribute(element, "class").casefold()
                # Avoid matching arbitrary hrefs; a URL containing "review"
                # alone does not prove this element is the review tab.
                label = " ".join([visible_text, aria, classes])
                if not any(word in label for word in (
                    "đánh giá", "nhận xét", "review", "rating"
                )):
                    continue

                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", element
                )
                try:
                    element.click()
                except (ElementClickInterceptedException, WebDriverException):
                    driver.execute_script("arguments[0].click();", element)

                logger.info("Clicked review tab/control: %s", label[:160])
                try:
                    WebDriverWait(driver, 8).until(
                        lambda d: visible_review_count() > 0
                    )
                    return True
                except TimeoutException:
                    continue
            except (StaleElementReferenceException, WebDriverException):
                continue

    # Progressive scrolling triggers lazy rendering on some product pages.
    try:
        for _ in range(3):
            page_height = driver.execute_script(
                "return Math.max(document.body.scrollHeight, "
                "document.documentElement.scrollHeight);"
            )
            viewport_height = driver.execute_script(
                "return window.innerHeight || 800;"
            )
            step = max(450, int(viewport_height * 0.7))
            for y in range(0, int(page_height) + step, step):
                driver.execute_script("window.scrollTo(0, arguments[0]);", y)
                time.sleep(0.35)
                if visible_review_count() > 0:
                    logger.info("Review cards appeared after scrolling to y=%s", y)
                    return True

            # Return to the widget area and allow a little time for async render.
            containers = driver.find_elements(By.CSS_SELECTOR, ".hrv-crv-container")
            if containers:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", containers[-1]
                )
            try:
                WebDriverWait(driver, 5).until(
                    lambda d: visible_review_count() > 0
                )
                return True
            except TimeoutException:
                pass
    except WebDriverException as exc:
        logger.debug("Progressive scroll for review widget failed: %s", exc)

    count = visible_review_count()
    logger.info("Review DOM diagnostic after activation attempts: %s", dom_diagnostic())
    return count > 0


def dump_review_diagnostics(driver, product_url):
    """Save a small HTML snapshot of raw review nodes when validation fails."""
    try:
        raw_items = driver.find_elements(By.CSS_SELECTOR, REVIEW_ITEM_SELECTOR)
        if not raw_items:
            return
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", urlparse(product_url).path.strip("/"))[:90]
        diagnostic_path = OUTPUT_DIR / f"review_diagnostic_{safe_slug}.html"
        try:
            dom_summary = driver.execute_script("""
                const cards = [...document.querySelectorAll('.hrv-crv-rating__ritem')];
                return {
                  raw_cards: cards.length,
                  cards_with_name: cards.filter(c => (c.querySelector('.hrv-crv-ritem-header__name')?.innerText || '').trim()).length,
                  cards_with_date: cards.filter(c => (c.querySelector('.hrv-crv-ritem-header__date')?.innerText || '').trim()).length,
                  cards_with_review_id: cards.filter(c => !!c.querySelector('.hrv-crv-ritem__actions[data-rating-id]')).length,
                  rating_ids_in_dom: document.querySelectorAll('.hrv-crv-ritem__actions[data-rating-id]').length,
                  image_ids_in_dom: document.querySelectorAll('.hrv-crv-ritem__img-preview-item[data-rating-id]').length,
                  widget_count: document.querySelectorAll('.hrv-crv-container').length
                };
            """)
        except WebDriverException:
            dom_summary = {}
        chunks = [
            "<!doctype html><html><head><meta charset='utf-8'>",
            f"<title>Review diagnostic: {product_url}</title></head><body>",
            f"<h2>Product URL: {product_url}</h2>",
            f"<p>DOM summary: {dom_summary}</p>",
        ]
        for index, item in enumerate(raw_items[:5], start=1):
            try:
                outer_html = driver.execute_script(
                    "return arguments[0].outerHTML;", item
                )
                chunks.append(f"<h3>Raw review node {index}</h3><pre>")
                chunks.append(
                    (outer_html or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                chunks.append("</pre>")
            except WebDriverException:
                continue
        chunks.append("</body></html>")
        diagnostic_path.write_text("\n".join(chunks), encoding="utf-8")
        logger.warning("Saved review markup diagnostic to: %s", diagnostic_path)
    except (OSError, WebDriverException) as exc:
        logger.warning("Could not save review diagnostic: %s", exc)


def collect_product_reviews(driver, product):
    """Open one product page and collect its rendered reviews."""
    product_url = product["product_url"]

    logger.info(
        "Opening product: %s | %s",
        product.get("product_name", ""),
        product_url,
    )

    CURRENT_PRODUCT_STATS["pages_checked"] = 0
    CURRENT_PRODUCT_STATS["reviews_seen"] = 0

    last_navigation_error = None
    for attempt in range(1, 4):
        try:
            driver.get(product_url)
            # With eager page loading, wait for a real page body rather than all
            # network requests from third-party assets.
            WebDriverWait(driver, WAIT_SECONDS).until(
                lambda d: d.find_elements(By.TAG_NAME, "body")
            )
            last_navigation_error = None
            break
        except TimeoutException as exc:
            # Selenium may raise a navigation timeout after the document is already
            # usable. Continue only if a product document is present.
            try:
                has_body = bool(driver.find_elements(By.TAG_NAME, "body"))
                current_url = driver.current_url
            except WebDriverException:
                has_body, current_url = False, ""
            if has_body and "/products/" in current_url:
                logger.warning(
                    "Navigation timed out but product DOM is available; continuing: %s",
                    product_url,
                )
                last_navigation_error = None
                break
            last_navigation_error = exc
            logger.warning(
                "Open product attempt %s/3 timed out: %s", attempt, str(exc).splitlines()[0]
            )
            if attempt < 3:
                time.sleep(2 * attempt)
        except WebDriverException as exc:
            last_navigation_error = exc
            logger.warning(
                "Open product attempt %s/3 failed: %s", attempt, str(exc).splitlines()[0]
            )
            if attempt < 3:
                time.sleep(2 * attempt)

    if last_navigation_error is not None:
        logger.warning("Could not open product page after retries: %s", product_url)
        raise ProductNavigationError(
            f"Could not open product page after 3 attempts: {product_url}"
        ) from last_navigation_error

    pause()
    product = get_product_metadata(driver, product)

    # Activate review tabs and trigger lazy rendering before deciding that
    # a product has no rendered reviews.
    activated = activate_review_section(driver)
    raw_items_count = len(driver.find_elements(By.CSS_SELECTOR, REVIEW_ITEM_SELECTOR))
    valid_items_count = len(find_review_items(driver))
    logger.info(
        "Review widget check: activated=%s, raw review elements=%s, valid review cards=%s",
        activated, raw_items_count, valid_items_count,
    )

    all_reviews = {}
    previous_page_signature = None

    for page_number in range(
        1, MAX_REVIEW_PAGES_PER_PRODUCT + 1
    ):
        try:
            WebDriverWait(driver, WAIT_SECONDS).until(
                lambda d: len(find_review_items(d)) > 0
            )
        except TimeoutException:
            raw_count = len(driver.find_elements(By.CSS_SELECTOR, REVIEW_ITEM_SELECTOR))
            try:
                dom_diagnostic = driver.execute_script(
                    "return {cards: document.querySelectorAll(arguments[0]).length, "
                    "ids: document.querySelectorAll('.hrv-crv-ritem__actions[data-rating-id]').length, "
                    "containers: document.querySelectorAll('.hrv-crv-container').length};",
                    REVIEW_ITEM_SELECTOR,
                ) or {}
            except WebDriverException:
                dom_diagnostic = {}
            widget_count = len(driver.find_elements(
                By.CSS_SELECTOR, ".hrv-crv-container, .hrv-crv-container[data-product-id]"
            ))
            if raw_count:
                logger.warning(
                    "Found %s raw review elements but none passed the review-card validation "
                    "(expected name/date/review ID). Product: %s",
                    raw_count, product_url,
                )
                dump_review_diagnostics(driver, product_url)
            else:
                logger.info(
                    "No review cards rendered after activation/scroll "
                    "(widget containers=%s, JS DOM diagnostic=%s). Product may have delayed/changed markup: %s",
                    widget_count, dom_diagnostic, product_url,
                )
            break

        items = find_review_items(driver)
        page_records = []

        for item in items:
            record = extract_review_record(item, product)
            if record:
                page_records.append(record)
                all_reviews[record["review_key"]] = record

        page_signature = tuple(
            record["review_key"] for record in page_records
        )

        CURRENT_PRODUCT_STATS["pages_checked"] = page_number
        CURRENT_PRODUCT_STATS["reviews_seen"] += len(page_records)
        logger.info(
            "Product review page %s: %s visible items, "
            "%s unique records collected",
            page_number,
            len(items),
            len(all_reviews),
        )

        # If clicking a control does not change the visible reviews,
        # stop rather than repeatedly saving the same page.
        if (
            previous_page_signature is not None
            and page_signature == previous_page_signature
        ):
            logger.info("Review page did not change; stopping.")
            break

        previous_page_signature = page_signature

        if page_number >= MAX_REVIEW_PAGES_PER_PRODUCT:
            logger.warning(
                "Reached safety limit of %s review pages for this product; "
                "stopping even if more pages may exist.",
                MAX_REVIEW_PAGES_PER_PRODUCT,
            )
            break

        clicked = click_review_pagination(driver)

        if not clicked:
            logger.info(
                "No further review page was confirmed. "
                "Collected reviews from pages successfully rendered so far."
            )
            break

        pause()

    return list(all_reviews.values())


# =========================================================
# 8. CSV OUTPUT
# =========================================================

def ensure_output_schema():
    """Migrate an existing CSV safely when new columns are added.

    Existing review_id values cannot be reconstructed from review_key because
    review_key is a one-way hash, so older rows receive an empty review_id.
    The derived has_text field is populated from review_content.
    """
    if not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0:
        return

    try:
        with OUTPUT_FILE.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            old_fields = reader.fieldnames or []
            if old_fields == CSV_FIELDS:
                return
            old_rows = list(reader)

        temp_file = OUTPUT_FILE.with_suffix(".tmp")
        with temp_file.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for row in old_rows:
                # Preserve old values and fill new/derived columns where possible.
                row.setdefault("review_id", "")
                content = (row.get("review_content") or row.get("review_text") or "").strip()
                row.setdefault("has_text", bool(content))
                writer.writerow(row)
        temp_file.replace(OUTPUT_FILE)
        logger.info(
            "Migrated existing CSV schema. Historical review_id values remain blank "
            "because they cannot be recovered from review_key."
        )
    except (OSError, csv.Error) as exc:
        logger.exception("Could not migrate existing CSV schema: %s", exc)
        raise


def load_existing_keys():
    """Read prior output keys so reruns do not append duplicates."""
    existing = set()

    if not OUTPUT_FILE.exists():
        return existing

    try:
        with OUTPUT_FILE.open(
            "r", newline="", encoding="utf-8-sig"
        ) as file:
            reader = csv.DictReader(file)

            for row in reader:
                key = row.get("review_key", "")
                if key:
                    existing.add(key)

    except (OSError, csv.Error) as exc:
        logger.warning(
            "Could not read existing CSV for deduplication: %s",
            exc,
        )

    return existing


def save_reviews(records):
    """Append new records to CSV; preserve existing records."""
    if not records:
        logger.info("No new records to save.")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_output_schema()
    existing_keys = load_existing_keys()

    new_records = [
        record for record in records
        if record.get("review_key")
        and record["review_key"] not in existing_keys
    ]

    if not new_records:
        logger.info("All collected records already exist in CSV.")
        return 0

    file_exists = OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0

    with OUTPUT_FILE.open(
        "a", newline="", encoding="utf-8-sig"
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
        "Saved %s new reviews to %s",
        len(new_records),
        OUTPUT_FILE,
    )

    return len(new_records)


# =========================================================
# 9. RESUME SUPPORT + MAIN
# =========================================================

def load_successful_product_urls():
    """Load URLs previously completed with status=success from the audit log."""
    completed = set()
    if not PRODUCT_LOG_FILE.exists() or PRODUCT_LOG_FILE.stat().st_size == 0:
        return completed
    try:
        with PRODUCT_LOG_FILE.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if row.get("status", "").strip().lower() == "success":
                    url = (row.get("product_url") or "").strip()
                    if url:
                        completed.add(url)
    except (OSError, csv.Error) as exc:
        logger.warning("Could not read product log for resume: %s", exc)
    return completed



def _repair_signature(row):
    """Build a conservative matching signature from fields already in the CSV."""
    def norm(value):
        return " ".join(str(value or "").split()).strip().casefold()

    return (
        norm(row.get("reviewer_name")),
        norm(row.get("review_date")),
        norm(row.get("review_content")),
    )


def repair_caryophy_missing_review_ids(records):
    """
    Backfill missing source review IDs for historical Caryophy rows only when
    reviewer/date/content uniquely identify exactly one old row and one newly
    scraped row. Ambiguous matches are left untouched.
    """
    if not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0:
        logger.error("Cannot repair review_id: output CSV does not exist or is empty: %s", OUTPUT_FILE)
        return 0, 0

    ensure_output_schema()

    try:
        with OUTPUT_FILE.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames or CSV_FIELDS
            rows = list(reader)
    except (OSError, csv.Error) as exc:
        logger.exception("Could not read CSV for review_id repair: %s", exc)
        raise

    target_slug = "/products/caryophy-smart-sunscreen-50ml"
    old_by_signature = {}
    for idx, row in enumerate(rows):
        product_url = (row.get("product_url") or "").strip().lower()
        is_caryophy = target_slug in product_url
        if is_caryophy and not (row.get("review_id") or "").strip():
            old_by_signature.setdefault(_repair_signature(row), []).append(idx)

    new_by_signature = {}
    for record in records:
        if (record.get("review_id") or "").strip():
            new_by_signature.setdefault(_repair_signature(record), []).append(record)

    repaired = 0
    ambiguous = 0
    for signature, old_indices in old_by_signature.items():
        new_records = new_by_signature.get(signature, [])
        # Only repair a one-to-one match; don't guess when names/dates/text repeat.
        if len(old_indices) == 1 and len(new_records) == 1:
            row = rows[old_indices[0]]
            record = new_records[0]
            review_id = str(record.get("review_id") or "").strip()
            product_id = str(row.get("product_id") or record.get("product_id") or "").strip()
            if review_id and product_id:
                row["review_id"] = review_id
                row["review_key"] = hashlib.sha256(
                    f"thegioiskinfood|{product_id}|{review_id}".encode("utf-8")
                ).hexdigest()[:24]
                repaired += 1
        elif old_indices:
            ambiguous += len(old_indices)

    # Write atomically so a failed write does not destroy the current CSV.
    temp_file = OUTPUT_FILE.with_suffix(".repair.tmp")
    try:
        with temp_file.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        temp_file.replace(OUTPUT_FILE)
    except (OSError, csv.Error):
        logger.exception("Could not write repaired CSV; original should remain untouched.")
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    logger.info(
        "Caryophy review_id repair finished: repaired=%s, ambiguous_or_unmatched=%s",
        repaired, ambiguous
    )
    logger.info("Updated CSV in place: %s", OUTPUT_FILE)
    return repaired, ambiguous

def main():
    global MAX_PRODUCTS, MAX_REVIEW_PAGES_PER_PRODUCT, CATEGORY_PAGE_COUNT
    parser = argparse.ArgumentParser(
        description="Collect Thegioiskinfood sunscreen reviews with per-product logging."
    )
    parser.add_argument(
        "--max-products", type=int, default=MAX_PRODUCTS,
        help="Tổng số sản phẩm tối đa lấy từ danh mục (mặc định: cấu hình hiện tại).",
    )
    parser.add_argument(
        "--start-product", type=int, default=1,
        help="Bắt đầu từ số thứ tự sản phẩm trong danh sách danh mục (mặc định: 1).",
    )
    parser.add_argument(
        "--max-review-pages", type=int, default=MAX_REVIEW_PAGES_PER_PRODUCT,
        help="Giới hạn số trang review mỗi sản phẩm (mặc định 40).",
    )
    parser.add_argument(
        "--category-pages", type=int, default=CATEGORY_PAGE_COUNT,
        help="Số trang danh mục dùng để khám phá sản phẩm (mặc định 3).",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Bỏ qua sản phẩm đã có trạng thái success trong product log; thử lại error/no_reviews.",
    )
    parser.add_argument(
        "--repair-caryophy-review-ids", action="store_true",
        help="Thu thập lại Caryophy và bổ sung review_id cho dòng lịch sử còn thiếu khi khớp duy nhất.",
    )
    args = parser.parse_args()
    if args.max_products < 1:
        parser.error("--max-products phải >= 1")
    if args.start_product < 1:
        parser.error("--start-product phải >= 1")
    if args.start_product > args.max_products:
        parser.error("--start-product không được lớn hơn --max-products")
    if args.max_review_pages < 1:
        parser.error("--max-review-pages phải >= 1")
    if args.category_pages < 1:
        parser.error("--category-pages phải >= 1")
    MAX_PRODUCTS = args.max_products
    MAX_REVIEW_PAGES_PER_PRODUCT = args.max_review_pages
    CATEGORY_PAGE_COUNT = args.category_pages

    driver = None
    total_collected = 0
    total_saved = 0
    products_processed = 0

    try:
        preflight_product_log_writable()
        driver = create_driver()

        if args.repair_caryophy_review_ids:
            logger.info("Repair mode: re-collecting Caryophy reviews to backfill missing source review_id values.")
            repair_product = dict(CARYOPHY_TEST_PRODUCT)
            repair_records = collect_product_reviews(driver, repair_product)
            repaired, ambiguous = repair_caryophy_missing_review_ids(repair_records)
            logger.info("Repair summary: repaired=%s, left unchanged because ambiguous/unmatched=%s", repaired, ambiguous)
            return

        if USE_CARYOPHY_TEST_PRODUCT:
            products = [dict(CARYOPHY_TEST_PRODUCT)]
            logger.info("Pilot mode: testing the known Caryophy review page first.")
        else:
            products = collect_products(driver)

        # Keep the original catalog order and slice by 1-based product number.
        catalog_total = len(products)
        products = products[:args.max_products]
        if args.start_product > len(products):
            logger.warning(
                "Start product %s is beyond the %s products selected from catalog (%s discovered).",
                args.start_product, len(products), catalog_total,
            )
            return
        products = products[args.start_product - 1:]
        logger.info(
            "Starting at catalog product %s; queued %s products (up to catalog position %s).",
            args.start_product, len(products), min(args.max_products, catalog_total),
        )

        if args.resume and products:
            completed_urls = load_successful_product_urls()
            before_count = len(products)
            products = [p for p in products if p.get("product_url") not in completed_urls]
            logger.info(
                "Resume mode: skipped %s previously successful products; %s remain.",
                before_count - len(products), len(products),
            )

        if not products:
            logger.warning(
                "No products discovered. Check category selectors "
                "and the category page HTML."
            )
            return

        logger.info("Products queued for this run: %s", len(products))
        existing_before = len(load_existing_keys())
        logger.info("Existing deduplication keys before run: %s", existing_before)

        for index, product in enumerate(products, start=args.start_product):
            product_name = product.get("product_name", "")
            product_url = product.get("product_url", "")
            product_id = product.get("product_id", "")
            started = datetime.now().astimezone().isoformat(timespec="seconds")
            status = "error"
            message = ""
            records = []
            saved_this_product = 0
            CURRENT_PRODUCT_STATS["pages_checked"] = 0
            CURRENT_PRODUCT_STATS["reviews_seen"] = 0

            logger.info("Processing product %s/%s", index, min(args.max_products, catalog_total))
            try:
                recovered = False
                for recovery_attempt in range(MAX_PRODUCT_RECOVERY_ATTEMPTS + 1):
                    try:
                        records = collect_product_reviews(driver, product)
                        break
                    except (ProductNavigationError, TimeoutException, WebDriverException) as exc:
                        if recovery_attempt >= MAX_PRODUCT_RECOVERY_ATTEMPTS:
                            raise
                        logger.warning(
                            "Product failed on recovery cycle %s/%s (%s). Restarting Chrome and retrying current product: %s",
                            recovery_attempt + 1, MAX_PRODUCT_RECOVERY_ATTEMPTS,
                            type(exc).__name__, product_url,
                        )
                        driver = restart_driver(driver)
                        recovered = True
                if recovered:
                    logger.info("Product completed after browser recovery: %s", product_url)
                total_collected += len(records)
                products_processed += 1
                saved_this_product = save_reviews(records)
                total_saved += saved_this_product
                status = "success" if records else "no_reviews"
                message = (
                    "OK" if records else
                    "No valid review records were extracted. Check raw-element/widget diagnostics; "
                    "this does not prove the product has zero customer reviews."
                )
                logger.info("Collected %s records for this product", len(records))
            except KeyboardInterrupt:
                status = "interrupted"
                message = "Stopped by user; completed products have been checkpointed."
                raise
            except Exception as exc:
                status = "error"
                message = f"{type(exc).__name__}: {exc}"
                logger.exception("Unexpected error for product: %s", product_url)
                # Keep the batch moving even if this product remains unavailable.
                try:
                    driver = restart_driver(driver)
                except Exception as restart_exc:
                    logger.exception("Could not restart Chrome after product failure: %s", restart_exc)
                    status = "error_driver_restart_failed"
                    message += f" | driver restart failed: {restart_exc}"
            finally:
                try:
                    append_product_log({
                        "time": started, "source": "thegioiskinfood",
                        "category": "sunscreen", "product_name": product_name,
                        "product_url": product_url, "source_product_id": product_id,
                        "status": status,
                        "pages_checked": CURRENT_PRODUCT_STATS["pages_checked"],
                        "reviews_seen": CURRENT_PRODUCT_STATS["reviews_seen"],
                        "reviews_added": saved_this_product, "message": message,
                    })
                except Exception:
                    logger.exception("Could not append product-level CSV log")
            pause()

        logger.info("=" * 60)
        logger.info("RUN COMPLETED")
        logger.info("Products processed: %s", products_processed)
        logger.info("Review records collected: %s", total_collected)
        logger.info("New records saved: %s", total_saved)
        logger.info("CSV: %s", OUTPUT_FILE)
        logger.info("Text log: %s", LOG_FILE)
        logger.info("Product log CSV: %s", PRODUCT_LOG_FILE)
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.warning("Stopped by user.")
    except Exception:
        logger.exception("Collector failed.")
        raise
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
