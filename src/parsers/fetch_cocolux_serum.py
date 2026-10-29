"""
Fetch rendered Cocolux serum category HTML and save it for later parsing.

Project: BEAUTYPRICE_INTELLIGENCE
Expected location:
    src/parsers/fetch_cocolux_serum.py

Run from project root:
    python src/parsers/fetch_cocolux_serum.py

Optional:
    python src/parsers/fetch_cocolux_serum.py --max-clicks 10 --delay 2
    python src/parsers/fetch_cocolux_serum.py --headless

Behavior:
- Opens the Cocolux serum category page in Chrome.
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

BASE_URL = "https://cocolux.com/danh-muc/serum-tinh-chat-i.112"
CATEGORY_MARKER = "/danh-muc/serum-tinh-chat-i.112"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "cocolux" / "html" / "serum"

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
    path = OUT_DIR / f"cocolux_serum_page_{page_number}.html"
    path.write_text(html, encoding="utf-8")
    return path


def current_page_number(current_url: str) -> int:
    """Read the ?page=N query parameter; the base category is page 1."""
    match = re.search(r"(?:\?|&)page=(\d+)(?:&|$)", current_url)
    return int(match.group(1)) if match else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Cocolux serum category HTML with Selenium."
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

    driver = None
    saved_files: list[Path] = []
    total_clicks = 0
    seen_urls: set[str] = set()
    saved_page_numbers: set[int] = set()

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("COCOLUX SERUM HTML FETCH")
        print(f"Category URL: {BASE_URL}")
        print(f"Output directory: {OUT_DIR}")
        print(f"Maximum 'Xem thêm' clicks: {args.max_clicks}")
        print("HTML only; no product parsing, review-text collection, or price-history updates.")

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
            print("STOP: verification/challenge page detected. No bypass attempted.")
            print(f"Current URL: {current_url}")
            return 2

        if "cocolux.com" not in urlparse(current_url).netloc.lower() or CATEGORY_MARKER not in current_url:
            print("STOP: browser did not remain on the expected Cocolux serum category page.")
            print(f"Current URL: {current_url}")
            return 2

        first_urls = product_urls(driver)
        card_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
        link_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_LINK_SELECTOR))
        fallback_link_count = len(driver.find_elements(By.CSS_SELECTOR, FALLBACK_PRODUCT_LINK_SELECTOR))
        print(f"Initial page title: {title}")
        print(f"Initial current URL: {current_url}")
        print(f"Initial card matches: {card_count}; product-link matches: {link_count}; fallback product-ID links: {fallback_link_count}; recognized product URLs: {len(first_urls)}")

        if not first_urls:
            dom_diagnostics(driver)
            # Save the page for diagnosis when we are still on the genuine category
            # URL. This is still Fetch-only and avoids losing the evidence needed
            # to understand a transient/partially rendered DOM.
            diagnostic_path = save_html(driver.page_source, 1)
            print(f"DIAGNOSTIC HTML saved (not confirmed for Parse): {diagnostic_path.name}")
            print("STOP: no recognizable product URLs in rendered DOM; inspect the diagnostic output before changing selectors again.")
            return 2

        page_number = current_page_number(current_url)
        path = save_html(driver.page_source, page_number)
        saved_files.append(path)
        saved_page_numbers.add(page_number)
        seen_urls.update(first_urls)
        print(f"[page {page_number}] Saved HTML: {path.name}; cards={card_count}; product URLs={len(first_urls)}")

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
                old_page = current_page_number(old_url)
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
                    print("STOP: verification/challenge page detected after clicking. No bypass attempted.")
                    break

                if "cocolux.com" not in urlparse(current_url).netloc.lower() or CATEGORY_MARKER not in current_url:
                    print("STOP: browser left the expected Cocolux category page.")
                    print(f"Current URL: {current_url}")
                    break

                current_urls = product_urls(driver)
                current_page = current_page_number(current_url)
                if not current_urls:
                    print("STOP: no recognizable product URLs found after clicking 'Xem thêm'.")
                    print(f"Current URL: {current_url}")
                    break

                # Save only when a new page state is reached. If the site appends
                # cards without changing the URL, number the next snapshot in order.
                if current_page == old_page and current_urls.issubset(old_urls):
                    print("STOP: clicking 'Xem thêm' produced no new page or product URLs.")
                    break
                if current_page == old_page:
                    current_page = max(saved_page_numbers, default=old_page) + 1

                if current_page in saved_page_numbers:
                    print(f"STOP: page {current_page} was already saved in this run; avoiding overwrite.")
                    break

                path = save_html(driver.page_source, current_page)
                saved_files.append(path)
                saved_page_numbers.add(current_page)
                new_urls = current_urls - seen_urls
                seen_urls.update(current_urls)
                total_clicks += 1
                card_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
                print(
                    f"[page {current_page}] Saved HTML after click {click_number}: {path.name}; "
                    f"rendered cards={card_count}; URLs on current state={len(current_urls)}; "
                    f"new URLs across run={len(new_urls)}; current URL={driver.current_url}"
                )

            except (StaleElementReferenceException, WebDriverException) as exc:
                print(f"STOP: browser interaction failed safely: {type(exc).__name__}: {exc}")
                break

        print("\nFETCH SUMMARY")
        print(f"HTML files saved this run: {len(saved_files)}")
        print(f"'Xem thêm' clicks completed: {total_clicks}")
        print(f"Unique product URLs seen across saved states: {len(seen_urls)}")
        print(f"Output directory: {OUT_DIR}")
        print("Note: pages may be separate results or cumulative snapshots; Parse should deduplicate by product URL.")
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


