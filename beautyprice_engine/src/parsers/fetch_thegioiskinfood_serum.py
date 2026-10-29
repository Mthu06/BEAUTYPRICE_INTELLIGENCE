"""Fetch rendered serum search results from The Gioi Skin Food and save HTML only.

Run from the project root:
    python src/parsers/fetch_thegioiskinfood_serum.py

Optional:
    python src/parsers/fetch_thegioiskinfood_serum.py --max-clicks 5
    python src/parsers/fetch_thegioiskinfood_serum.py --headless

This script only opens the search page, clicks the normal "Xem thêm sản phẩm"
button, and saves the final rendered HTML. It does not parse products or update
catalog/price history. If a verification page appears, it stops without bypassing it.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

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

URL = "https://thegioiskinfood.com/search?type=product&q=serum+d%C6%B0%E1%BB%A1ng"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "thegioiskinfood" / "html" / "serum"
OUTPUT_FILE = OUTPUT_DIR / "thegioiskinfood_serum_search_serum_duong.html"
CARD_SELECTOR = 'a.tgsfw-card[href*="/products/"]'
MORE_SELECTOR = "button.tgsfw-more"
CHALLENGE_MARKERS = (
    "verify you are human",
    "checking your browser",
    "unusual traffic",
    "captcha",
    "access denied",
)


def get_product_count(driver) -> int:
    """Count product cards currently rendered in the search results."""
    return len(driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR))


def has_challenge_page(driver) -> bool:
    """Detect obvious access challenges; do not attempt to bypass them."""
    title = (driver.title or "").lower()
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text[:5000].lower()
    except WebDriverException:
        body_text = ""
    return any(word in title or word in body_text for word in CHALLENGE_MARKERS)


def wait_for_more_cards(driver, old_count: int, timeout: int) -> bool:
    """Wait for new cards or for the load-more button to disappear/become hidden."""
    def condition(d):
        if get_product_count(d) > old_count:
            return True
        buttons = d.find_elements(By.CSS_SELECTOR, MORE_SELECTOR)
        return not buttons or not buttons[0].is_displayed()

    try:
        WebDriverWait(driver, timeout).until(condition)
    except (TimeoutException, StaleElementReferenceException):
        pass
    return get_product_count(driver) > old_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch The Gioi Skin Food serum search HTML (no parsing)."
    )
    parser.add_argument("--max-clicks", type=int, default=10,
                        help="Maximum clicks on 'Xem thêm sản phẩm' (default: 10).")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to wait after page/card updates (default: 2).")
    parser.add_argument("--timeout", type=int, default=35,
                        help="Wait timeout in seconds (default: 35).")
    parser.add_argument("--headless", action="store_true",
                        help="Run Chrome without showing its window.")
    args = parser.parse_args()

    if args.max_clicks < 0:
        parser.error("--max-clicks must be >= 0")
    if args.delay < 0.5:
        parser.error("--delay must be >= 0.5 seconds")
    if args.timeout < 10:
        parser.error("--timeout must be >= 10 seconds")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--lang=vi-VN")
    options.add_argument("--disable-notifications")
    if args.headless:
        options.add_argument("--headless=new")

    driver = None
    click_count = 0
    status = "OK"
    initial_count = 0

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("=" * 60)
        print("FETCH THE GIOI SKINFOOD - SERUM SEARCH")
        print(f"URL: {URL}")
        print(f"HTML output: {OUTPUT_FILE}")
        print("Mode: save rendered HTML only; no parsing/history update.")
        print("=" * 60)

        driver.get(URL)
        wait.until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))
        try:
            wait.until(lambda d: get_product_count(d) > 0 or has_challenge_page(d))
        except TimeoutException:
            print("WARNING: no product cards appeared before timeout.")

        time.sleep(args.delay)
        if has_challenge_page(driver):
            print("STOP: a possible verification/access challenge was detected.")
            print("No challenge was bypassed and no output was saved.")
            return 2

        initial_count = get_product_count(driver)
        print(f"Initial product cards: {initial_count}")
        if initial_count == 0:
            print("ERROR: no product cards found. Check the page manually in Chrome.")
            return 1

        for step in range(1, args.max_clicks + 1):
            buttons = driver.find_elements(By.CSS_SELECTOR, MORE_SELECTOR)
            if not buttons or not buttons[0].is_displayed():
                print("'Xem thêm sản phẩm' button is absent/hidden; stopping.")
                break

            before = get_product_count(driver)
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", buttons[0])
                time.sleep(0.3)
                buttons[0].click()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                time.sleep(0.7)
                buttons = driver.find_elements(By.CSS_SELECTOR, MORE_SELECTOR)
                if not buttons:
                    print("Button disappeared before retry; stopping.")
                    break
                try:
                    driver.execute_script("arguments[0].click();", buttons[0])
                except WebDriverException as exc:
                    print(f"WARNING: click failed: {exc}")
                    status = "PARTIAL"
                    break
            except WebDriverException as exc:
                print(f"WARNING: click failed: {exc}")
                status = "PARTIAL"
                break

            increased = wait_for_more_cards(driver, before, args.timeout)
            time.sleep(args.delay)
            after = get_product_count(driver)

            if has_challenge_page(driver):
                print("STOP: possible verification/access challenge after click.")
                print("No challenge was bypassed and no output was saved.")
                return 2

            if increased or after > before:
                click_count += 1
                print(f"Click {step}: {before} -> {after} product cards")
            else:
                print(f"Click {step}: no new cards ({after} total). Stopping.")
                status = "PARTIAL" if buttons else status
                break

        final_count = get_product_count(driver)
        html = driver.page_source or ""
        if len(html) < 1000:
            print("ERROR: rendered HTML is empty/too short; no file saved.")
            return 1

        OUTPUT_FILE.write_text(html, encoding="utf-8")
        print("\nFETCH SUMMARY")
        print(f"Initial cards: {initial_count}")
        print(f"Successful load-more clicks: {click_count}")
        print(f"Final cards: {final_count}")
        print(f"HTML size: {len(html):,} characters")
        print(f"Status: {status}")
        print(f"Saved: {OUTPUT_FILE}")
        print("Reminder: this script does not create CSVs or change price_snapshots.csv.")
        return 0 if final_count > 0 else 1

    except WebDriverException as exc:
        print(f"ERROR: Selenium/Chrome failed: {exc}")
        print("Check Chrome installation, Selenium version, and whether Chrome can open normally.")
        return 1
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())

