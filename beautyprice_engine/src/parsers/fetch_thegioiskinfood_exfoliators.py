"""
Fetch rendered The Gioi Skin Food exfoliators collection pages with Selenium.

Run from the project root:
    python src/parsers/fetch_thegioiskinfood_exfoliators.py

Optional:
    python src/parsers/fetch_thegioiskinfood_exfoliators.py --max-pages 2
    python src/parsers/fetch_thegioiskinfood_exfoliators.py --start-page 1 --max-pages 2
    python src/parsers/fetch_thegioiskinfood_exfoliators.py --max-pages 2 --headless

Requirements:
    python -m pip install -U selenium

This saves browser-rendered HTML for inspection/parsing only. It does not parse
products, collect review text, update catalog files, or bypass access controls.
If a verification/challenge page appears, stop.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = (
    "https://thegioiskinfood.com/collections/tay-da-chet"
    "?sort=quantity-descending&prices=0%2C100000000"
    "&types=T%E1%BA%A8Y%20DA%20CH%E1%BA%BET"
)
CATEGORY_MARKER = "tay-da-chet"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "thegioiskinfood" / "html" / "exfoliators"


def build_page_url(page: int) -> str:
    """Keep the supplied collection filters while selecting a page."""
    parts = urlsplit(BASE_URL)
    params = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
              if key.lower() != "page"]
    if page > 1:
        params.append(("page", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch The Gioi Skin Food exfoliators collection HTML with Selenium."
    )
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument(
        "--headless", action="store_true",
        help="Run Chrome headlessly; initially leave this off to observe the browser."
    )
    args = ap.parse_args()

    if args.start_page < 1:
        ap.error("--start-page must be >= 1")
    if args.max_pages < 1:
        ap.error("--max-pages must be >= 1")
    if args.delay < 1:
        ap.error("--delay must be >= 1 second")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    options = Options()
    if args.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--lang=vi-VN")
    options.add_argument("--disable-notifications")

    driver = None
    saved: list[int] = []
    failed: list[tuple[int, str]] = []
    total_cards = 0
    total_links = 0
    end_page = args.start_page + args.max_pages - 1

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("THE GIOI SKINFOOD EXFOLIATORS SELENIUM FETCH")
        print(f"Category URL: {BASE_URL}")
        print(f"Target pages: {args.start_page}..{end_page}")
        print(f"Output directory: {OUT_DIR}")
        print("HTML only: no parsing, review-text collection, or price-history updates.")

        for page in range(args.start_page, end_page + 1):
            url = build_page_url(page)
            print(f"\n[{page - args.start_page + 1}/{args.max_pages}] Opening {url}")
            load_timed_out = False
            try:
                try:
                    driver.get(url)
                except TimeoutException:
                    load_timed_out = True
                    print("WARNING: page-load timeout; checking whether rendered page is usable.")

                wait.until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))
                try:
                    wait.until(lambda d: len(d.find_elements(
                        By.CSS_SELECTOR, ".proLoop a[href*='/products/']"
                    )) > 0)
                except TimeoutException:
                    pass

                title = driver.title or ""
                current_url = driver.current_url or ""
                body_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                block_markers = (
                    "verify you are human", "checking your browser", "access denied",
                    "unusual traffic", "captcha", "xác minh bạn không phải",
                    "truy cập bị từ chối",
                )
                if any(marker in body_text for marker in block_markers):
                    failed.append((page, "verification/block page; stopped"))
                    print("STOP: possible verification/block page. Respecting site access controls.")
                    break

                if CATEGORY_MARKER not in (title + " " + current_url).lower():
                    failed.append((page, "unexpected title/URL; verify category"))
                    print(f"WARNING: title/URL does not clearly indicate exfoliators: {title!r}")

                cards = driver.find_elements(By.CSS_SELECTOR, ".proLoop")
                links = driver.find_elements(By.CSS_SELECTOR, ".proLoop a[href*='/products/']")
                if not links:
                    failed.append((page, "no rendered product links; saved page for inspection"))
                    print(f"WARNING: no rendered product links detected. Title: {title!r}")

                html = driver.page_source or ""
                if len(html) < 1000:
                    failed.append((page, "page_source empty or unexpectedly short; not saved"))
                    print("ERROR: HTML is empty or unexpectedly short; not saving this page.")
                    break

                out = OUT_DIR / f"thegioiskinfood_exfoliators_page_{page}.html"
                out.write_text(html, encoding="utf-8")
                saved.append(page)
                total_cards += len(cards)
                total_links += len(links)
                timeout_note = " | page-load timeout noted" if load_timed_out else ""
                print(f"Saved {out.name} | title={title!r} | product cards={len(cards)} | product links={len(links)}{timeout_note}")
            except WebDriverException as exc:
                failed.append((page, f"browser error: {exc.__class__.__name__}: {exc}"))
                print(f"ERROR on page {page}: {exc.__class__.__name__}: {exc}")
                if "invalid session id" in str(exc).lower():
                    break

            if page < end_page:
                time.sleep(args.delay)

        print("\nFETCH SUMMARY")
        print(f"Pages saved: {len(saved)}/{args.max_pages}")
        print(f"Product cards counted (duplicates not removed): {total_cards}")
        print(f"Product links counted (may include duplicates): {total_links}")
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

    print("\nFetcher finished. Inspect the saved HTML before writing the exfoliators parser.")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())

