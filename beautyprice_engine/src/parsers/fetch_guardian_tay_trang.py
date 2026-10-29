"""Fetch rendered Guardian Tẩy Trang category pages and save HTML for inspection.

Run from the project root:
    python src/parsers/fetch_guardian_tay_trang.py --max-pages 3

Optional:
    python src/parsers/fetch_guardian_tay_trang.py --start-page 1 --max-pages 3 --timeout 45
    python src/parsers/fetch_guardian_tay_trang.py --max-pages 3 --headless

Requirements:
    python -m pip install -U selenium

This script saves HTML only. It does not parse products, collect reviews, or bypass
site access controls. If a verification/challenge page appears, it stops.
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

BASE_URL = "https://www.guardian.com.vn/cham-soc-da-mat/tay-trang.html"
CATEGORY_MARKER = "tay-trang"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "guardian" / "html" / "tay_trang"


def build_page_url(page: int) -> str:
    """Guardian page 1 uses the clean URL; page 2+ uses ?p=N."""
    return BASE_URL if page == 1 else f"{BASE_URL}?p={page}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Guardian Tẩy Trang category HTML with Selenium."
    )
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument(
        "--headless", action="store_true",
        help="Run Chrome headlessly; initially leave this off to observe the browser."
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
    # Eager waits for the initial HTML/DOM, not every analytics/image resource.
    # Product cards may still render later, so we also wait for product links below.
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
        driver.set_script_timeout(min(args.timeout, 30))
        wait = WebDriverWait(driver, args.timeout)

        print("GUARDIAN TAY TRANG HTML FETCH")
        print(f"Category URL: {BASE_URL}")
        print(f"Target pages: {args.start_page}..{end_page}")
        print(f"Output directory: {OUT_DIR}")
        print("HTML only; no product parsing or review collection.")

        for page in range(args.start_page, end_page + 1):
            url = build_page_url(page)
            print(f"\n[{page - args.start_page + 1}/{args.max_pages}] Opening {url}")
            load_timed_out = False
            try:
                try:
                    driver.get(url)
                except TimeoutException as exc:
                    # A page-load timeout does not always mean the DOM is unusable.
                    # Try to inspect/save it, but record the timeout for QA.
                    load_timed_out = True
                    failed.append((page, f"page-load timeout; checking available DOM ({exc.__class__.__name__})"))
                    print("WARNING: page-load timeout; checking whether the page DOM is usable.")

                try:
                    wait.until(
                        lambda d: d.execute_script("return document.readyState")
                        in ("interactive", "complete")
                    )
                except TimeoutException:
                    print("WARNING: document.readyState did not settle before timeout.")

                try:
                    wait.until(
                        lambda d: len(d.find_elements(
                            By.CSS_SELECTOR, "li.product-item a.product-item-link"
                        )) > 0
                    )
                except TimeoutException:
                    pass  # Save HTML for diagnosis if product links are absent.

                title = driver.title or ""
                current_url = driver.current_url or ""
                try:
                    body_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                except WebDriverException:
                    body_text = ""

                block_markers = (
                    "verify you are human", "checking your browser", "access denied",
                    "unusual traffic", "captcha", "xác minh bạn không phải",
                    "truy cập bị từ chối",
                )
                if any(marker in body_text for marker in block_markers):
                    failed.append((page, "verification/block page; stopped"))
                    print("STOP: possible verification/block page. Respecting site access controls.")
                    break

                category_text = (title + " " + current_url).lower()
                if CATEGORY_MARKER not in category_text:
                    failed.append((page, "unexpected title/URL; verify category"))
                    print(f"WARNING: title/URL does not clearly indicate tẩy trang: {title!r}")

                cards = driver.find_elements(By.CSS_SELECTOR, "li.product-item")
                links = driver.find_elements(
                    By.CSS_SELECTOR, "li.product-item a.product-item-link"
                )
                if not links:
                    failed.append((page, "no rendered product links"))
                    print(f"WARNING: no product links detected. Title: {title!r}")

                html = driver.page_source
                if not html or len(html) < 1000:
                    failed.append((page, "page_source empty or unexpectedly short; not saved"))
                    print("ERROR: available HTML is empty or unexpectedly short; not saving this page.")
                    break

                out = OUT_DIR / f"guardian_tay_trang_page_{page}.html"
                out.write_text(html, encoding="utf-8")
                saved.append(page)
                total_cards += len(cards)
                timeout_note = " | page-load timeout noted" if load_timed_out else ""
                print(
                    f"Saved {out.name} | title={title!r} "
                    f"| product cards={len(cards)} | product links={len(links)}{timeout_note}"
                )

            except WebDriverException as exc:
                failed.append((page, f"browser error: {exc.__class__.__name__}: {exc}"))
                print(f"ERROR on page {page}: {exc.__class__.__name__}: {exc}")
                # If the browser session/renderer is no longer usable, don't keep retrying pages.
                break

            if page < end_page:
                time.sleep(args.delay)

        print("\nFETCH SUMMARY")
        print(f"Pages saved: {len(saved)}/{args.max_pages}")
        print(f"Product cards counted (duplicates not removed): {total_cards}")
        if failed:
            print("Pages needing review:")
            for page, reason in failed:
                print(f" - page {page}: {reason}")

    except WebDriverException as exc:
        print("Could not start or control Chrome WebDriver.")
        print(f"Details: {exc}")
        print("Check Chrome is installed, then run: python -m pip install -U selenium")
        return 1
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass

    print("\nFetcher finished. Inspect saved HTML before writing a Guardian tẩy trang parser.")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())

