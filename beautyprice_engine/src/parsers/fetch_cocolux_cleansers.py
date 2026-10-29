"""
Fetch rendered Cocolux facial-cleanser category HTML and save it for later parsing.

Project: BEAUTYPRICE_INTELLIGENCE
Expected location:
    src/parsers/fetch_cocolux_cleansers.py

Run from project root:
    python src/parsers/fetch_cocolux_cleansers.py

Optional:
    python src/parsers/fetch_cocolux_cleansers.py --max-clicks 10 --delay 2
    python src/parsers/fetch_cocolux_cleansers.py --headless

Behavior:
- Opens the Cocolux facial-cleanser category page in Chrome.
- Saves the initial rendered HTML, then clicks the page's "Xem thêm" control.
- Saves each rendered state as a separate HTML file.
- The page states are cumulative: later files may contain cards saved in earlier
  files too. The parser should deduplicate by canonical product URL.
- Saves HTML only. It does not parse products, collect review text, or update
  catalog/price history.
- If a verification/challenge page appears, stops without attempting to bypass it.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from src.utils.collection_logger import CollectionLogger

BASE_URL = "https://cocolux.com/danh-muc/sua-rua-mat-i.108"
CATEGORY_MARKER = "/danh-muc/sua-rua-mat-i.108"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "cocolux" / "html" / "cleansers"

PRODUCT_CARD_SELECTOR = ".list-product-index .item.item-product, .list-product-index .item-product, .item.item-product"
PRODUCT_LINK_SELECTOR = '.item-product a[href], .item.item-product a[href]'
FALLBACK_PRODUCT_LINK_SELECTOR = 'a[href*="-i."]'
LOAD_MORE_SELECTOR = ".view-all-index.more_product"


def is_verification_page(title: str, current_url: str, body_text: str) -> bool:
    """Conservative check for common challenge/verification pages."""
    text = f"{title}\n{current_url}\n{body_text}".lower()
    phrases = (
        "captcha",
        "verify you are human",
        "access denied",
        "robot check",
        "unusual traffic",
        "security check",
        "xác minh bạn không phải",
        "xác nhận bạn không phải",
    )
    return any(phrase in text for phrase in phrases)


def product_urls(driver) -> set[str]:
    """Find category product URLs, preferring anchors inside product cards."""
    urls: set[str] = set()
    anchors = []
    try:
        anchors = driver.find_elements(By.CSS_SELECTOR, PRODUCT_LINK_SELECTOR)
    except WebDriverException:
        pass

    # Some live renders place product anchors outside the expected wrapper, even
    # though the supplied saved HTML has .list-product-index > .item.item-product.
    # Fall back only to links with Cocolux's product-id suffix, not every site link.
    if not anchors:
        try:
            anchors = driver.find_elements(By.CSS_SELECTOR, FALLBACK_PRODUCT_LINK_SELECTOR)
        except WebDriverException:
            anchors = []

    for anchor in anchors:
        try:
            href = (anchor.get_attribute("href") or "").strip()
        except StaleElementReferenceException:
            continue
        if not href:
            continue
        absolute = urljoin(BASE_URL, href)
        parsed = urlparse(absolute)
        if parsed.netloc.lower().endswith("cocolux.com"):
            path = parsed.path.rstrip("/")
            if re.search(r"-i\.[A-Za-z0-9]+$", path, re.IGNORECASE):
                urls.add(f"https://{parsed.netloc.lower()}{path}")
    return urls


def dom_diagnostics(driver) -> None:
    """Print a small, non-sensitive diagnostic of rendered product-card markup."""
    for selector in (PRODUCT_CARD_SELECTOR, PRODUCT_LINK_SELECTOR, FALLBACK_PRODUCT_LINK_SELECTOR, LOAD_MORE_SELECTOR):
        try:
            print(f"DOM selector {selector!r}: {len(driver.find_elements(By.CSS_SELECTOR, selector))} match(es)")
        except WebDriverException as exc:
            print(f"DOM selector {selector!r}: ERROR {type(exc).__name__}")
    try:
        snippets = driver.execute_script("""
            const cards = Array.from(document.querySelectorAll('.item-product')).slice(0, 2);
            return cards.map(el => el.outerHTML.slice(0, 900));
        """) or []
        for i, snippet in enumerate(snippets, start=1):
            print(f"Rendered .item-product sample {i}: {snippet}")
    except WebDriverException:
        pass


def save_html(html: str, page_number: int) -> Path:
    """Save HTML to the first available filename without overwriting files."""
    candidate = max(1, page_number)

    while True:
        path = OUT_DIR / f"cocolux_cleansers_page_{candidate}.html"
        try:
            # Exclusive creation ('x') guarantees an existing snapshot is never overwritten.
            with path.open("x", encoding="utf-8") as file:
                file.write(html)
            return path
        except FileExistsError:
            candidate += 1


def snapshot_number(path: Path) -> int:
    """Return the numeric snapshot suffix from a saved HTML filename."""
    match = re.search(r"_page_(\d+)$", path.stem)
    if not match:
        raise ValueError(f"Unexpected Cocolux snapshot filename: {path.name}")
    return int(match.group(1))

def current_page_number(current_url: str) -> int:
    """Read the ?page=N query parameter; the base category is page 1."""
    match = re.search(r"(?:\?|&)page=(\d+)(?:&|$)", current_url)
    return int(match.group(1)) if match else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Cocolux facial-cleanser category HTML with Selenium."
    )
    parser.add_argument(
        "--max-clicks",
        type=int,
        default=20,
        help="Maximum number of 'Xem thêm' clicks after the initial page (default: 20).",
    )
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait after each click.")
    parser.add_argument("--timeout", type=int, default=30, help="Selenium wait timeout in seconds.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome headlessly; initially leave this off to observe the page.",
    )
    args = parser.parse_args()

    if args.max_clicks < 0:
        parser.error("--max-clicks must be >= 0")
    if args.delay < 1:
        parser.error("--delay must be >= 1 second")
    if args.timeout < 10:
        parser.error("--timeout must be >= 10 seconds")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    options = Options()
    options.page_load_strategy = "eager"
    if args.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1100")
    options.add_argument("--lang=vi-VN")
    options.add_argument("--disable-notifications")

    logger = CollectionLogger(
        retailer_id="cocolux",
        category="cleansers",
        stage="fetch",
        script_name=Path(__file__).name,
        output_file=str(OUT_DIR.relative_to(PROJECT_ROOT)),
    )

    driver = None
    saved_files: list[Path] = []
    total_clicks = 0
    seen_urls: set[str] = set()
    saved_snapshot_numbers: set[int] = set()
    failed = False
    error_message: str | None = None
    return_code = 0

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("COCOLUX CLEANSERS HTML FETCH")
        print(f"Category URL: {BASE_URL}")
        print(f"Output directory: {OUT_DIR}")
        print(f"Maximum 'Xem thêm' clicks: {args.max_clicks}")
        print("HTML only; no product parsing, review-text collection, or price-history updates.")

        logger.page_attempted()
        try:
            driver.get(BASE_URL)
        except TimeoutException:
            print("WARNING: page-load timeout; checking whether the rendered DOM is usable.")

        try:
            wait.until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))
        except TimeoutException:
            print("WARNING: document.readyState did not settle before timeout.")

        try:
            wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
        except TimeoutException:
            pass

        title = driver.title or ""
        current_url = driver.current_url or ""
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text or ""
        except WebDriverException:
            body_text = ""

        if is_verification_page(title, current_url, body_text):
            failed = True
            return_code = 2
            error_message = "Verification/challenge page detected; no bypass attempted."
            logger.records_failed_add(1, error_message=error_message)
            print("STOP: verification/challenge page detected. No bypass attempted.")
            print(f"Current URL: {current_url}")
            return return_code

        if (
            "cocolux.com" not in urlparse(current_url).netloc.lower()
            or CATEGORY_MARKER not in current_url
        ):
            failed = True
            return_code = 2
            error_message = "Browser left the expected Cocolux cleanser category."
            logger.records_failed_add(1, error_message=error_message)
            print("STOP: browser did not remain on the expected Cocolux facial-cleanser category page.")
            print(f"Current URL: {current_url}")
            return return_code

        first_urls = product_urls(driver)
        card_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
        link_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_LINK_SELECTOR))
        fallback_link_count = len(driver.find_elements(By.CSS_SELECTOR, FALLBACK_PRODUCT_LINK_SELECTOR))
        print(f"Initial page title: {title}")
        print(f"Initial current URL: {current_url}")
        print(
            f"Initial card matches: {card_count}; product-link matches: {link_count}; "
            f"fallback product-ID links: {fallback_link_count}; recognized product URLs: {len(first_urls)}"
        )

        if not first_urls:
            dom_diagnostics(driver)
            # Preserve a diagnostic snapshot, but do not count it as a parse-ready page.
            diagnostic_path = save_html(driver.page_source, 1)
            logger.page_saved(count=1, output_file=str(diagnostic_path.relative_to(PROJECT_ROOT)))
            failed = True
            return_code = 2
            error_message = "No recognizable product URLs in rendered DOM; diagnostic HTML saved."
            logger.records_failed_add(1, error_message=error_message)
            print(f"DIAGNOSTIC HTML saved (not confirmed for Parse): {diagnostic_path.name}")
            print("STOP: no recognizable product URLs in rendered DOM; inspect the diagnostic output before changing selectors again.")
            return return_code

        source_page = current_page_number(current_url)
        path = save_html(driver.page_source, source_page)
        snapshot_id = snapshot_number(path)
        saved_files.append(path)
        saved_snapshot_numbers.add(snapshot_id)
        logger.page_saved(count=1, output_file=str(path.relative_to(PROJECT_ROOT)))
        logger.records_found_add(len(first_urls))
        seen_urls.update(first_urls)
        print(
            f"[source page {source_page}; snapshot {snapshot_id}] Saved HTML: {path.name}; "
            f"cards={card_count}; product URLs={len(first_urls)}"
        )

        for click_number in range(1, args.max_clicks + 1):
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, LOAD_MORE_SELECTOR)
                if not buttons:
                    print("STOP: 'Xem thêm' control no longer exists; no further page states available.")
                    break

                button = buttons[0]
                if not button.is_displayed():
                    print("STOP: 'Xem thêm' control is not visible; stopping without bypassing the page.")
                    break

                old_url = driver.current_url
                old_page = current_page_number(old_url)
                old_urls = product_urls(driver)
                old_button_page = button.get_attribute("data-page")

                # A click represents an attempt to obtain another rendered page state.
                logger.page_attempted()
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                    button,
                )
                time.sleep(0.3)
                try:
                    button.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", button)

                # Cocolux may update the query string (?page=2) and replace the
                # product grid, rather than append cards to the existing DOM.
                try:
                    wait.until(
                        lambda d: (
                            d.current_url != old_url
                            or (
                                len(product_urls(d)) > len(old_urls)
                                and (
                                    not old_button_page
                                    or (
                                        d.find_elements(By.CSS_SELECTOR, LOAD_MORE_SELECTOR)
                                        and d.find_elements(By.CSS_SELECTOR, LOAD_MORE_SELECTOR)[0].get_attribute("data-page") != old_button_page
                                    )
                                )
                            )
                        )
                    )
                except (TimeoutException, StaleElementReferenceException):
                    time.sleep(args.delay)

                time.sleep(args.delay)
                title = driver.title or ""
                current_url = driver.current_url or ""
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text or ""
                except WebDriverException:
                    body_text = ""

                if is_verification_page(title, current_url, body_text):
                    failed = True
                    return_code = 2
                    error_message = "Verification/challenge page detected after clicking; no bypass attempted."
                    logger.records_failed_add(1, error_message=error_message)
                    print("STOP: verification/challenge page detected after clicking. No bypass attempted.")
                    break

                if (
                    "cocolux.com" not in urlparse(current_url).netloc.lower()
                    or CATEGORY_MARKER not in current_url
                ):
                    failed = True
                    return_code = 2
                    error_message = "Browser left the expected Cocolux category page after clicking."
                    logger.records_failed_add(1, error_message=error_message)
                    print("STOP: browser left the expected Cocolux category page.")
                    print(f"Current URL: {current_url}")
                    break

                current_urls = product_urls(driver)
                source_page = current_page_number(current_url)
                if not current_urls:
                    failed = True
                    return_code = 2
                    error_message = "No recognizable product URLs found after clicking 'Xem thêm'."
                    logger.records_failed_add(1, error_message=error_message)
                    print("STOP: no recognizable product URLs found after clicking 'Xem thêm'.")
                    print(f"Current URL: {current_url}")
                    break

                if source_page == old_page and current_urls.issubset(old_urls):
                    # No new content is not automatically a fatal error: it may be the end
                    # of the category. Stop safely and retain the snapshots already saved.
                    print("STOP: clicking 'Xem thêm' produced no new page or product URLs.")
                    break

                # If the URL is unchanged but products were appended, number this as the
                # next snapshot. save_html() then advances further if a prior file exists.
                requested_snapshot = source_page
                if source_page == old_page:
                    requested_snapshot = max(saved_snapshot_numbers, default=old_page) + 1

                path = save_html(driver.page_source, requested_snapshot)
                snapshot_id = snapshot_number(path)
                saved_files.append(path)
                saved_snapshot_numbers.add(snapshot_id)
                logger.page_saved(count=1, output_file=str(path.relative_to(PROJECT_ROOT)))
                new_urls = current_urls - seen_urls
                if new_urls:
                    logger.records_found_add(len(new_urls))
                seen_urls.update(current_urls)
                total_clicks += 1
                card_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
                print(
                    f"[source page {source_page}; snapshot {snapshot_id}] Saved HTML after click "
                    f"{click_number}: {path.name}; rendered cards={card_count}; "
                    f"URLs on current state={len(current_urls)}; new URLs across run={len(new_urls)}; "
                    f"current URL={driver.current_url}"
                )

            except (StaleElementReferenceException, WebDriverException) as exc:
                failed = True
                return_code = 1
                error_message = f"Browser interaction failed: {type(exc).__name__}: {exc}"
                logger.records_failed_add(1, error_message=error_message)
                print(f"STOP: browser interaction failed safely: {error_message}")
                break

        print("\nFETCH SUMMARY")
        print(f"HTML files saved this run: {len(saved_files)}")
        print(f"'Xem thêm' clicks completed: {total_clicks}")
        print(f"Unique product URLs seen across saved states: {len(seen_urls)}")
        print(f"Output directory: {OUT_DIR}")
        print("Note: pages may be separate results or cumulative snapshots; Parse should deduplicate by product URL.")
        return return_code

    except WebDriverException as exc:
        failed = True
        return_code = 1
        error_message = f"{type(exc).__name__}: {exc}"
        logger.records_failed_add(1, error_message=error_message)
        print(f"ERROR: Selenium/Chrome failed: {error_message}")
        print("Check that Chrome and Selenium are installed, then retry manually.")
        return return_code
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException as exc:
                failed = True
                return_code = 1
                error_message = error_message or f"Chrome shutdown error: {exc}"

        if failed:
            status = "partial" if saved_files else "failed"
        elif saved_files:
            status = "success"
        else:
            status = "failed"
            error_message = error_message or "No new HTML files were saved."

        logger.finish(status=status, error_message=error_message)



if __name__ == "__main__":
    raise SystemExit(main())


