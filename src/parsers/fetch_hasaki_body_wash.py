"""
Fetch rendered Hasaki Sữa Tắm category pages using Selenium/Chrome.

Run from the project root:
    python src/parsers/fetch_hasaki_body_wash.py --max-pages 2

Optional:
    python src/parsers/fetch_hasaki_body_wash.py --max-pages 3
    python src/parsers/fetch_hasaki_body_wash.py --max-pages 3 --headless

Requirements:
    pip install selenium

This saves browser-rendered HTML for inspection/parsing only.
It does not parse products, update catalog files, or bypass access controls.
If Hasaki presents a verification/challenge page, stop and inspect manually.
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


BASE_URL = "https://hasaki.vn/danh-muc/sua-tam-xa-bong-tam-c26.html"
CATEGORY_SLUG = "sua-tam-xa-bong-tam-c26"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "hasaki" / "html" / "sua_tam"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch Hasaki Sữa Tắm category HTML with Selenium."
    )
    ap.add_argument("--max-pages", type=int, default=9)
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome headlessly; initially leave off to observe the browser.",
    )
    args = ap.parse_args()

    if args.max_pages < 1:
        ap.error("--max-pages must be >= 1")
    if args.start_page < 1:
        ap.error("--start-page must be >= 1")
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
    total_links = 0

    try:
        # Uses Selenium Manager built into modern Selenium; no webdriver_manager import needed.
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        wait = WebDriverWait(driver, args.timeout)

        print("HASAKI SỮA TẮM SELENIUM FETCH")
        print(f"Category URL: {BASE_URL}")
        print(
            f"Target pages: {args.start_page}.."
            f"{args.start_page + args.max_pages - 1}"
        )
        print(f"Output: {OUT_DIR}")
        print("HTML only: no parsing and no catalog/price-history updates.")

        for page in range(args.start_page, args.start_page + args.max_pages):
            url = f"{BASE_URL}?p={page}"
            print(f"\\n[{page - args.start_page + 1}/{args.max_pages}] Opening {url}")

            try:
                driver.get(url)
                wait.until(
                    lambda d: d.execute_script("return document.readyState")
                    in ("interactive", "complete")
                )

                # Wait for product anchors; if none appear, keep the page for diagnosis.
                try:
                    wait.until(
                        lambda d: len(
                            d.find_elements(By.CSS_SELECTOR, 'a[href*="/san-pham/"]')
                        ) > 0
                    )
                except TimeoutException:
                    pass

                title = driver.title or ""
                current_url = driver.current_url or ""
                page_text = (
                    driver.find_element(By.TAG_NAME, "body").text or ""
                ).lower()

                if any(
                    marker in page_text
                    for marker in (
                        "verify you are human",
                        "checking your browser",
                        "access denied",
                        "unusual traffic",
                        "captcha",
                        "xác minh bạn không phải",
                        "truy cập bị từ chối",
                    )
                ):
                    failed.append((page, "verification/block page; stopped"))
                    print(
                        "STOP: possible verification/block page. "
                        "Respecting site access controls."
                    )
                    break

                category_text = (title + " " + current_url).lower()
                if CATEGORY_SLUG not in category_text:
                    failed.append((page, "unexpected title/URL; verify category"))
                    print(f"WARNING: title/URL not clearly Sữa Tắm category: {title}")

                count = len(
                    driver.find_elements(By.CSS_SELECTOR, 'a[href*="/san-pham/"]')
                )
                if count == 0:
                    failed.append((page, "no rendered product links"))
                    print(f"WARNING: no product links detected. Title: {title}")

                out = OUT_DIR / f"sua_tam_page_{page}.html"
                out.write_text(driver.page_source, encoding="utf-8")
                saved.append(page)
                total_links += count
                print(
                    f"Saved {out.name} | title={title!r} "
                    f"| rendered product links={count}"
                )

            except WebDriverException as exc:
                failed.append(
                    (page, f"browser error: {exc.__class__.__name__}: {exc}")
                )
                print(f"ERROR on page {page}: {exc.__class__.__name__}: {exc}")
                break

            if page < args.start_page + args.max_pages - 1:
                time.sleep(args.delay)

        print("\\nFETCH SUMMARY")
        print(f"Pages saved: {len(saved)}/{args.max_pages}")
        print(
            "Rendered product links counted (including duplicates): "
            f"{total_links}"
        )
        if failed:
            print("Pages needing review:")
            for page, reason in failed:
                print(f" - page {page}: {reason}")

    except WebDriverException as exc:
        print("Could not start Chrome WebDriver.")
        print(f"Details: {exc}")
        print("Check that Chrome is installed and update Selenium with:")
        print("python -m pip install -U selenium")
        return 1
    finally:
        if driver is not None:
            driver.quit()

    print("\\nFetcher finished. Inspect saved HTML before writing/running a parser.")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())

