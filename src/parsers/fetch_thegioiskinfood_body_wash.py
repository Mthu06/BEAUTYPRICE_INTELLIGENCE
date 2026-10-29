"""
Fetch rendered The Gioi Skin Food Sữa Tắm collection pages and save HTML only.

Run from the project root:
    python src/parsers/fetch_thegioiskinfood_body_wash.py

Optional:
    python src/parsers/fetch_thegioiskinfood_body_wash.py --start-page 1 --max-pages 2
    python src/parsers/fetch_thegioiskinfood_body_wash.py --max-pages 2 --headless

Requirements:
    python -m pip install -U selenium

This script saves browser-rendered HTML only. It does not parse products, collect review
text, update catalog/price history, or bypass access controls. If a verification/challenge
page appears, stop and inspect manually.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = "https://thegioiskinfood.com/collections/sua-tam"
CATEGORY_MARKER = "/collections/sua-tam"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "thegioiskinfood" / "html" / "body_wash"

# The supplied HTML uses .collection-itemloop > .proLoop product cards.
PRODUCT_LINK_SELECTOR = 'a[href*="/products/"]'
PRODUCT_CARD_SELECTOR = ".collection-itemloop .proLoop"


def build_page_url(page: int) -> str:
    """Page 1 uses the clean collection URL; page 2+ uses ?page=N."""
    return BASE_URL if page == 1 else f"{BASE_URL}?page={page}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch The Gioi Skin Food Sữa Tắm collection HTML with Selenium."
    )
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=35)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome headlessly; initially leave this off to observe the browser.",
    )
    args = parser.parse_args()

    if args.start_page < 1:
        parser.error("--start-page must be >= 1")
    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.delay < 1:
        parser.error("--delay must be >= 1 second")
    if args.timeout < 10:
        parser.error("--timeout must be >= 10 seconds")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    options = Options()
    options.page_load_strategy = "eager"
    if args.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--lang=vi-VN")
    options.add_argument("--disable-notifications")

    driver = None
    saved: list[int] = []
    failed: list[tuple[int, str]] = []
    total_cards = 0
    end_page = args.start_page + args.max_pages - 1

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("THE GIOI SKINFOOD BODY WASH HTML FETCH")
        print(f"Category URL: {BASE_URL}")
        print(f"Target pages: {args.start_page}..{end_page}")
        print(f"Output directory: {OUT_DIR}")
        print("HTML only; no product parsing or review text collection.")

        for page in range(args.start_page, end_page + 1):
            url = build_page_url(page)
            print(f"\n[{page - args.start_page + 1}/{args.max_pages}] Opening {url}")
            load_timed_out = False

            try:
                try:
                    driver.get(url)
                except TimeoutException:
                    load_timed_out = True
                    failed.append((page, "page-load timeout; checking available DOM"))
                    print("WARNING: page-load timeout; checking whether the DOM is usable.")

                try:
                    wait.until(
                        lambda d: d.execute_script("return document.readyState")
                        in ("interactive", "complete")
                    )
                except TimeoutException:
                    print("WARNING: document.readyState did not settle before timeout.")

                try:
                    wait.until(
                        lambda d: len(d.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR)) > 0
                    )
                except TimeoutException:
                    # Save usable HTML for diagnosis if no product cards appear.
                    pass

                title = driver.title or ""
                current_url = driver.current_url or ""
                try:
                    body_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                except WebDriverException:
                    body_text = ""

                challenge_terms = (
                    "verify you are human",
                    "checking your browser",
                    "captcha",
                    "unusual traffic",
                    "access denied",
                    "xác minh bạn là người",
                )
                if any(term in body_text for term in challenge_terms):
                    print(
                        "STOP: possible verification/challenge page detected. "
                        "No HTML saved for this page; inspect manually."
                    )
                    failed.append((page, "possible verification/challenge page"))
                    break

                if CATEGORY_MARKER not in current_url.lower():
                    print(f"WARNING: unexpected current URL: {current_url}")
                    failed.append((page, f"unexpected URL: {current_url}"))
                    continue

                html = driver.page_source
                if not html or len(html) < 1000:
                    failed.append((page, "page source empty or unexpectedly short"))
                    print("WARNING: page source is empty or unexpectedly short.")
                    continue

                output_path = OUT_DIR / f"thegioiskinfood_body_wash_page_{page}.html"
                output_path.write_text(html, encoding="utf-8")

                cards = driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR)
                product_links = driver.find_elements(By.CSS_SELECTOR, PRODUCT_LINK_SELECTOR)
                card_count = len(cards)
                total_cards += card_count
                saved.append(page)

                print(
                    f"Saved {output_path.name} | title={title!r} | "
                    f"product cards={card_count} | product links={len(product_links)}"
                )
                if card_count == 0:
                    failed.append((page, "saved HTML but no .proLoop product cards detected"))
                if load_timed_out:
                    print("NOTE: saved after page-load timeout; inspect this HTML carefully.")

            except WebDriverException as exc:
                message = str(exc).splitlines()[0][:240]
                failed.append((page, f"WebDriverException: {message}"))
                print(f"ERROR on page {page}: {message}")

            if page < end_page:
                time.sleep(args.delay)

        print("\nFETCH SUMMARY")
        print(f"Pages saved: {len(saved)}/{args.max_pages}")
        print(f"Saved page numbers: {saved}")
        print(f"Product cards counted (duplicates not removed): {total_cards}")
        if failed:
            print(f"Warnings/failures: {len(failed)}")
            for page, reason in failed:
                print(f"  - Page {page}: {reason}")
        else:
            print("Warnings/failures: 0")
        print("Fetcher finished. Inspect the saved HTML before writing/running the parser.")
        return 0 if saved else 1

    except WebDriverException as exc:
        print(f"Could not start or control Chrome: {str(exc).splitlines()[0]}")
        print("Check that Chrome is installed and Selenium is up to date.")
        return 1
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())

