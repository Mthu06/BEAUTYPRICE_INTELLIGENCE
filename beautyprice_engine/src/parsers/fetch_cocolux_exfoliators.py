"""
Fetch rendered Cocolux exfoliator search results and save HTML for later parsing.

Project: BEAUTYPRICE_INTELLIGENCE
Expected location:
    src/parsers/fetch_cocolux_exfoliators.py

Run from project root:
    python src/parsers/fetch_cocolux_exfoliators.py

Optional:
    python src/parsers/fetch_cocolux_exfoliators.py --max-clicks 10 --delay 2
    python src/parsers/fetch_cocolux_exfoliators.py --headless

Important:
- Starts from the Cocolux search results for "Tẩy Tế Bào Chết".
- Saves rendered HTML only. It does not parse products, collect review text,
  or update catalog/price history.
- The supplied observation says clicking "Xem thêm" may navigate to
  /danh-muc/tay-trang-i.107?page=2. That URL is for makeup remover, not
  exfoliators, so this script stops rather than accepting that page as valid
  exfoliator data. It saves the unexpected page as a diagnostic HTML file.
- If a verification/challenge page appears, stops without attempting to bypass it.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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

BASE_URL = (
    "https://cocolux.com/search"
    "?keyword=T%E1%BA%A9y+T%E1%BA%BF+B%C3%A0o+Ch%E1%BA%BFt"
)
EXPECTED_HOST = "cocolux.com"
EXPECTED_PATH = "/search"
EXPECTED_KEYWORD = "Tẩy Tế Bào Chết"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "cocolux" / "html" / "exfoliators"

PRODUCT_CARD_SELECTOR = (
    ".list-product-index .item.item-product, "
    ".list-product-index .item-product, "
    ".item.item-product"
)
PRODUCT_LINK_SELECTOR = ".item-product a[href]"
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


def is_expected_search_url(url: str) -> bool:
    """Return True only for Cocolux search results with the expected keyword."""
    parsed = urlparse(url)
    if parsed.hostname is None or not parsed.hostname.lower().endswith(EXPECTED_HOST):
        return False
    if parsed.path.rstrip("/") != EXPECTED_PATH:
        return False

    params = parse_qs(parsed.query)
    keyword = " ".join(params.get("keyword", [""])).strip().casefold()
    expected = EXPECTED_KEYWORD.casefold()
    return keyword == expected


def product_urls(driver) -> set[str]:
    """Find product-ID URLs inside product cards, with a narrow fallback."""
    urls: set[str] = set()
    try:
        anchors = driver.find_elements(By.CSS_SELECTOR, PRODUCT_LINK_SELECTOR)
    except WebDriverException:
        anchors = []

    # Only use the fallback when the expected card selector finds no links.
    if not anchors:
        try:
            anchors = driver.find_elements(
                By.CSS_SELECTOR, FALLBACK_PRODUCT_LINK_SELECTOR
            )
        except WebDriverException:
            anchors = []

    for anchor in anchors:
        try:
            href = (anchor.get_attribute("href") or "").strip()
        except StaleElementReferenceException:
            continue
        if not href:
            continue

        parsed = urlparse(href)
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")
        if (
            host.endswith(EXPECTED_HOST)
            and re.search(r"-i\.[A-Za-z0-9]+$", path, re.IGNORECASE)
        ):
            urls.add(f"https://{host}{path}")

    return urls


def dom_diagnostics(driver) -> None:
    """Print a small diagnostic of the rendered product-list structure."""
    for selector in (
        PRODUCT_CARD_SELECTOR,
        PRODUCT_LINK_SELECTOR,
        FALLBACK_PRODUCT_LINK_SELECTOR,
        LOAD_MORE_SELECTOR,
    ):
        try:
            count = len(driver.find_elements(By.CSS_SELECTOR, selector))
            print(f"DOM selector {selector!r}: {count} match(es)")
        except WebDriverException as exc:
            print(f"DOM selector {selector!r}: ERROR {type(exc).__name__}")

    try:
        snippets = driver.execute_script("""
            return Array.from(document.querySelectorAll('.item-product'))
                .slice(0, 2)
                .map(el => el.outerHTML.slice(0, 900));
        """) or []
        for i, snippet in enumerate(snippets, start=1):
            print(f"Rendered .item-product sample {i}: {snippet}")
    except WebDriverException:
        pass


def save_html(html: str, page_number: int, diagnostic: bool = False) -> Path:
    """Save one rendered state; diagnostic files are named separately."""
    if diagnostic:
        filename = f"cocolux_exfoliators_diagnostic_after_click_{page_number}.html"
    else:
        filename = f"cocolux_exfoliators_page_{page_number}.html"

    path = OUT_DIR / filename
    path.write_text(html, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Cocolux exfoliator search-result HTML with Selenium."
    )
    parser.add_argument(
        "--max-clicks",
        type=int,
        default=20,
        help="Maximum 'Xem thêm' clicks after the initial page (default: 20).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait after each click (minimum 1).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Selenium wait timeout in seconds (minimum 10).",
    )
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

    driver = None
    saved_files: list[Path] = []
    seen_urls: set[str] = set()
    successful_clicks = 0

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("COCOLUX EXFOLIATORS HTML FETCH")
        print(f"Search URL: {BASE_URL}")
        print(f"Output directory: {OUT_DIR}")
        print(f"Maximum 'Xem thêm' clicks: {args.max_clicks}")
        print("HTML only; no parsing, review-text collection, catalog rebuild, or price-history updates.")

        try:
            driver.get(BASE_URL)
        except TimeoutException:
            print("WARNING: page-load timeout; checking whether rendered DOM is usable.")

        try:
            wait.until(
                lambda d: d.execute_script("return document.readyState")
                in ("interactive", "complete")
            )
        except TimeoutException:
            print("WARNING: document.readyState did not settle before timeout.")

        try:
            wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
        except TimeoutException:
            print("WARNING: expected product-card selector did not appear before timeout.")

        title = driver.title or ""
        current_url = driver.current_url or ""
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text or ""
        except WebDriverException:
            body_text = ""

        if is_verification_page(title, current_url, body_text):
            print("STOP: verification/challenge page detected. No bypass attempted.")
            print(f"Current URL: {current_url}")
            return 2

        if not is_expected_search_url(current_url):
            print("STOP: browser did not remain on the expected exfoliator search URL.")
            print(f"Expected search URL pattern: {BASE_URL}")
            print(f"Current URL: {current_url}")
            return 2

        first_urls = product_urls(driver)
        card_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
        print(f"Initial page title: {title}")
        print(f"Initial current URL: {current_url}")
        print(f"Initial card matches: {card_count}")
        print(f"Recognized product URLs: {len(first_urls)}")

        if not first_urls:
            dom_diagnostics(driver)
            diagnostic_path = save_html(driver.page_source, 1, diagnostic=True)
            print(f"DIAGNOSTIC HTML saved: {diagnostic_path.name}")
            print("STOP: no recognizable product URLs; inspect the HTML before changing selectors.")
            return 2

        path = save_html(driver.page_source, 1)
        saved_files.append(path)
        seen_urls.update(first_urls)
        print(
            f"[search state 1] Saved HTML: {path.name}; "
            f"cards={card_count}; product URLs={len(first_urls)}"
        )

        for click_number in range(1, args.max_clicks + 1):
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, LOAD_MORE_SELECTOR)
                if not buttons:
                    print("STOP: 'Xem thêm' control no longer exists.")
                    break

                button = buttons[0]
                if not button.is_displayed():
                    print("STOP: 'Xem thêm' control is not visible.")
                    break

                old_url = driver.current_url
                old_urls = product_urls(driver)
                old_button_page = button.get_attribute("data-page")

                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                    button,
                )
                time.sleep(0.3)

                try:
                    button.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", button)

                try:
                    wait.until(
                        lambda d: (
                            d.current_url != old_url
                            or len(product_urls(d)) > len(old_urls)
                            or (
                                d.find_elements(By.CSS_SELECTOR, LOAD_MORE_SELECTOR)
                                and d.find_elements(By.CSS_SELECTOR, LOAD_MORE_SELECTOR)[0]
                                .get_attribute("data-page") != old_button_page
                            )
                        )
                    )
                except (TimeoutException, StaleElementReferenceException):
                    time.sleep(args.delay)

                time.sleep(args.delay)
                current_url = driver.current_url or ""
                title = driver.title or ""
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text or ""
                except WebDriverException:
                    body_text = ""

                if is_verification_page(title, current_url, body_text):
                    print("STOP: verification/challenge page detected after clicking. No bypass attempted.")
                    break

                # The user observed this button navigating to the makeup-remover
                # category. Preserve evidence for inspection, but never count it
                # as a valid exfoliator page or continue clicking on it.
                if not is_expected_search_url(current_url):
                    diagnostic_path = save_html(
                        driver.page_source, click_number + 1, diagnostic=True
                    )
                    print("STOP: 'Xem thêm' navigated away from the expected search results.")
                    print(f"URL before click: {old_url}")
                    print(f"URL after click:  {current_url}")
                    print(f"Unexpected state saved for diagnosis: {diagnostic_path.name}")
                    print("This state is NOT included as an exfoliator page.")
                    break

                current_urls = product_urls(driver)
                if not current_urls:
                    diagnostic_path = save_html(
                        driver.page_source, click_number + 1, diagnostic=True
                    )
                    print("STOP: no recognizable product URLs after clicking.")
                    print(f"Diagnostic HTML saved: {diagnostic_path.name}")
                    break

                if current_urls.issubset(old_urls):
                    print("STOP: click produced no new product URLs.")
                    break

                page_number = click_number + 1
                path = save_html(driver.page_source, page_number)
                saved_files.append(path)
                new_urls = current_urls - seen_urls
                seen_urls.update(current_urls)
                successful_clicks += 1
                card_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
                print(
                    f"[search state {page_number}] Saved HTML: {path.name}; "
                    f"rendered cards={card_count}; URLs on state={len(current_urls)}; "
                    f"new URLs across run={len(new_urls)}; URL={current_url}"
                )

            except (StaleElementReferenceException, WebDriverException) as exc:
                print(f"STOP: browser interaction failed safely: {type(exc).__name__}: {exc}")
                break

        print("\nFETCH SUMMARY")
        print(f"Valid search HTML files saved this run: {len(saved_files)}")
        print(f"'Xem thêm' clicks yielding valid new search states: {successful_clicks}")
        print(f"Unique product URLs seen in valid search states: {len(seen_urls)}")
        print(f"Output directory: {OUT_DIR}")
        print("Check any diagnostic HTML manually before running Parse.")
        print("No catalog rebuild or price-history update was performed.")
        return 0

    except WebDriverException as exc:
        print(f"ERROR: Selenium/Chrome failed: {type(exc).__name__}: {exc}")
        print("Check that Chrome and Selenium are installed, then retry manually.")
        return 1
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())

