
"""
Fetch rendered Guardian cleanser category pages and save HTML for inspection.

Run from the project root:
    python src/parsers/fetch_guardian_cleansers.py --max-pages 3

Optional:
    python src/parsers/fetch_guardian_cleansers.py --start-page 1 --max-pages 3
    python src/parsers/fetch_guardian_cleansers.py --max-pages 3 --headless
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

from src.utils.collection_logger import CollectionLogger

BASE_URL = "https://www.guardian.com.vn/cham-soc-da-mat/sua-rua-mat.html"
CATEGORY_MARKER = "sua-rua-mat"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "guardian" / "html" / "sua_rua_mat"
SCRIPT_NAME = Path(__file__).name


def build_page_url(page: int) -> str:
    """Guardian page 1 uses the clean URL; page 2+ uses ?p=N."""
    return BASE_URL if page == 1 else f"{BASE_URL}?p={page}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Guardian cleanser category HTML with Selenium."
    )
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome headlessly.",
    )
    args = parser.parse_args()

    if args.start_page < 1:
        parser.error("--start-page must be >= 1")
    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.delay < 1:
        parser.error("--delay must be >= 1 second")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    end_page = args.start_page + args.max_pages - 1
    saved: list[int] = []
    failed: list[tuple[int, str]] = []
    total_product_cards = 0
    driver = None
    status = "failed"
    error_message = None

    logger = CollectionLogger(
        retailer_id="guardian",
        category="cleansers",
        stage="fetch",
        script_name=SCRIPT_NAME,
        output_file=str(OUT_DIR.relative_to(ROOT)),
    )

    try:
        options = Options()
        if args.headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--lang=vi-VN")
        options.add_argument("--disable-notifications")

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("GUARDIAN CLEANSER HTML FETCH")
        print(f"Category URL: {BASE_URL}")
        print(f"Target pages: {args.start_page}..{end_page}")
        print(f"Output directory: {OUT_DIR}")
        print("HTML only; no product parsing or review collection.")

        for page in range(args.start_page, end_page + 1):
            out = OUT_DIR / f"guardian_sua_rua_mat_page_{page}.html"

            # Never replace existing HTML without an explicit review.
            if out.exists():
                reason = f"HTML already exists; skipped to protect existing file: {out.name}"
                failed.append((page, reason))
                logger.records_skipped_add(1, reason=reason)
                print(f"SKIP page {page}: {reason}")
                continue

            url = build_page_url(page)
            logger.page_attempted()
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
                    pass  # Keep the existing diagnostic behavior.

                title = driver.title or ""
                current_url = driver.current_url or ""
                body_text = (
                    driver.find_element(By.TAG_NAME, "body").text or ""
                ).lower()

                block_markers = (
                    "verify you are human",
                    "checking your browser",
                    "access denied",
                    "unusual traffic",
                    "captcha",
                    "xác minh bạn không phải",
                    "truy cập bị từ chối",
                )
                if any(marker in body_text for marker in block_markers):
                    reason = "Verification/block page; stopped to respect site access controls."
                    failed.append((page, reason))
                    logger.records_failed_add(1, error_message=reason)
                    print(f"STOP: {reason}")
                    break

                category_ok = CATEGORY_MARKER in (
                    title + " " + current_url
                ).lower()
                if not category_ok:
                    reason = "Unexpected title/URL; verify category."
                    failed.append((page, reason))
                    logger.records_failed_add(1, error_message=reason)
                    print(f"WARNING: {reason} Title: {title}")

                cards = driver.find_elements(By.CSS_SELECTOR, "li.product-item")
                links = driver.find_elements(
                    By.CSS_SELECTOR, "li.product-item a.product-item-link"
                )

                if not links:
                    reason = "No rendered product links detected."
                    failed.append((page, reason))
                    logger.records_failed_add(1, error_message=reason)
                    print(f"WARNING: {reason} Title: {title}")
                    # Do not treat an empty/challenge page as a successful capture.
                    continue

                # Exclusive creation prevents accidental overwrites.
                try:
                    with out.open("x", encoding="utf-8") as file:
                        file.write(driver.page_source)
                except FileExistsError:
                    reason = f"File appeared during run; skipped: {out.name}"
                    failed.append((page, reason))
                    logger.records_skipped_add(1, reason=reason)
                    print(f"SKIP page {page}: {reason}")
                    continue

                saved.append(page)
                total_product_cards += len(cards)
                logger.page_saved(output_file=str(out.relative_to(ROOT)))
                print(
                    f"Saved {out.name} | title={title!r} "
                    f"| product cards={len(cards)} | product links={len(links)}"
                )

            except WebDriverException as exc:
                reason = f"Browser error: {exc.__class__.__name__}: {exc}"
                failed.append((page, reason))
                logger.records_failed_add(1, error_message=reason)
                print(f"ERROR on page {page}: {reason}")
                break

            if page < end_page:
                time.sleep(args.delay)

        print("\nFETCH SUMMARY")
        print(f"Pages attempted: {logger.pages_attempted}")
        print(f"Pages saved: {len(saved)}")
        print(f"Product cards counted (duplicates not removed): {total_product_cards}")

        if failed:
            print("Pages needing review:")
            for page, reason in failed:
                print(f" - page {page}: {reason}")

        skipped_only = (
            not saved
            and logger.records_skipped > 0
            and logger.records_failed == 0
        )

        if failed and saved:
            status = "partial"
        elif failed and not skipped_only:
            status = "failed"
        elif saved or skipped_only:
            status = "success"
            if skipped_only:
                error_message = (
                    "No new pages fetched; existing HTML files were preserved."
                )
        else:
            status = "failed"
            error_message = "No new pages were saved."

    except WebDriverException as exc:
        error_message = f"{exc.__class__.__name__}: {exc}"
        print("Could not start or use Chrome WebDriver.")
        print(f"Details: {error_message}")
        status = "failed"

    except Exception as exc:
        error_message = f"{exc.__class__.__name__}: {exc}"
        status = "failed"
        raise

    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass

        logger.finish(status=status, error_message=error_message)

    print(f"\nFetcher finished with status: {status}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

