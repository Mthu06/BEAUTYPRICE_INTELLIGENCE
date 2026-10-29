"""
Fetch rendered Guardian sunscreen category pages and save the HTML for inspection.

Run from the project root:
    python src/parsers/fetch_guardian_sunscreens.py --max-pages 2

Optional:
    python src/parsers/fetch_guardian_sunscreens.py --start-page 1 --max-pages 2
    python src/parsers/fetch_guardian_sunscreens.py --max-pages 2 --headless

Requirements:
    python -m pip install -U selenium

Notes:
- Uses Selenium because the supplied Guardian HTML files contain rendered product cards.
- Saves HTML only; it does not parse products or collect customer reviews.
- Does not bypass access controls. If a verification/challenge page appears, stop.
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

BASE_URL = "https://www.guardian.com.vn/cham-soc-da-mat/chong-nang.html"
CATEGORY_MARKER = "chong-nang"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "guardian" / "html" / "chong_nang"


def build_page_url(page: int) -> str:
    """Guardian page 1 uses the clean URL; page 2+ uses ?p=N."""
    return BASE_URL if page == 1 else f"{BASE_URL}?p={page}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Guardian sunscreen category HTML with Selenium."
    )
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=25)
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
    total_product_cards = 0
    end_page = args.start_page + args.max_pages - 1

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("GUARDIAN SUNSCREEN HTML FETCH")
        print(f"Category URL: {BASE_URL}")
        print(f"Target pages: {args.start_page}..{end_page}")
        print(f"Output directory: {OUT_DIR}")
        print("HTML only; no product parsing or review collection.")

        for page in range(args.start_page, end_page + 1):
            url = build_page_url(page)
            print(f"\n[{page - args.start_page + 1}/{args.max_pages}] Opening {url}")
            try:
                driver.get(url)
                wait.until(
                    lambda d: d.execute_script("return document.readyState")
                    in ("interactive", "complete")
                )
                try:
                    wait.until(
                        lambda d: len(d.find_elements(
                            By.CSS_SELECTOR, "li.product-item a.product-item-link"
                        )) > 0
                    )
                except TimeoutException:
                    pass  # Save the page for diagnosis if product cards are absent.

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
                    print(f"WARNING: title/URL does not clearly indicate sunscreen category: {title}")

                cards = driver.find_elements(By.CSS_SELECTOR, "li.product-item")
                links = driver.find_elements(
                    By.CSS_SELECTOR, "li.product-item a.product-item-link"
                )
                if not links:
                    failed.append((page, "no rendered product links"))
                    print(f"WARNING: no product links detected. Title: {title}")

                out = OUT_DIR / f"guardian_chong_nang_page_{page}.html"
                out.write_text(driver.page_source, encoding="utf-8")
                saved.append(page)
                total_product_cards += len(cards)
                print(
                    f"Saved {out.name} | title={title!r} "
                    f"| product cards={len(cards)} | product links={len(links)}"
                )
            except WebDriverException as exc:
                failed.append((page, f"browser error: {exc.__class__.__name__}: {exc}"))
                print(f"ERROR on page {page}: {exc.__class__.__name__}: {exc}")
                break

            if page < end_page:
                time.sleep(args.delay)

        print("\nFETCH SUMMARY")
        print(f"Pages saved: {len(saved)}/{args.max_pages}")
        print(f"Product cards counted (duplicates not removed): {total_product_cards}")
        if failed:
            print("Pages needing review:")
            for page, reason in failed:
                print(f" - page {page}: {reason}")

    except WebDriverException as exc:
        print("Could not start Chrome WebDriver.")
        print(f"Details: {exc}")
        print("Check Chrome is installed, then run: python -m pip install -U selenium")
        return 1
    finally:
        if driver is not None:
            driver.quit()

    print("\nFetcher finished. Inspect the saved HTML before writing a Guardian parser.")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())

