"""
Fetch rendered Hasaki body exfoliator category pages using Selenium/Chrome.

Run from project root:
    python src/parsers/fetch_hasaki_exfoliators.py

Optional:
    python src/parsers/fetch_hasaki_exfoliators.py --max-pages 3
    python src/parsers/fetch_hasaki_exfoliators.py --max-pages 3 --headless

Requirements:
    pip install selenium

This saves browser-rendered HTML for inspection/parsing. It does not bypass
access controls. If the site presents a challenge or blocks access, stop.
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


BASE_URL = "https://hasaki.vn/danh-muc/tay-te-bao-chet-toan-than-c128.html"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "hasaki" / "html" / "tay_te_bao_chet_body"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch Hasaki body exfoliator category HTML with Selenium."
    )
    ap.add_argument("--max-pages", type=int, default=9)
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
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, args.timeout)

        print("HASAKI BODY EXFOLIATOR SELENIUM FETCH")
        print(f"Category URL: {BASE_URL}")
        print(f"Target pages: 1..{args.max_pages}")
        print(f"Output: {OUT_DIR}")
        print("A Chrome window will open. If a verification/block page appears, stop.")

        for page in range(1, args.max_pages + 1):
            url = f"{BASE_URL}?p={page}"
            print(f"\n[{page}/{args.max_pages}] Opening {url}")

            try:
                driver.get(url)
                wait.until(
                    lambda d: d.execute_script("return document.readyState")
                    in ("interactive", "complete")
                )

                # Wait for rendered product links; save the page for diagnosis
                # if the product links do not appear before timeout.
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
                page_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()

                if any(
                    marker in page_text
                    for marker in (
                        "verify you are human",
                        "access denied",
                        "unusual traffic",
                        "captcha",
                    )
                ):
                    failed.append((page, "verification/block page; stopped"))
                    print(
                        "STOP: possible verification/block page. "
                        "Respecting site access controls."
                    )
                    break

                html = driver.page_source
                count = len(
                    driver.find_elements(By.CSS_SELECTOR, 'a[href*="/san-pham/"]')
                )

                category_text = (title + " " + current_url).lower()
                if "tay-te-bao-chet-toan-than" not in category_text:
                    failed.append((page, "unexpected title/URL; verify category"))
                    print(f"WARNING: title/URL not clearly body exfoliator: {title}")

                if count == 0:
                    failed.append((page, "no rendered product links"))
                    print(f"WARNING: no rendered product links. Title: {title}")

                out = OUT_DIR / f"tay_te_bao_chet_body_page_{page}.html"
                out.write_text(html, encoding="utf-8")
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
                if "invalid session id" in str(exc).lower():
                    break

            if page < args.max_pages:
                time.sleep(args.delay)

        print("\nFETCH SUMMARY")
        print(f"Pages saved: {len(saved)}/{args.max_pages}")
        print(f"Rendered product links counted (including duplicates): {total_links}")
        if failed:
            print("Pages needing review:")
            for page, reason in failed:
                print(f" - page {page}: {reason}")

    except WebDriverException as exc:
        print("Could not start Chrome WebDriver.")
        print(f"Details: {exc}")
        print("Check Chrome and Selenium installation: pip install -U selenium")
        return 1
    finally:
        if driver is not None:
            driver.quit()

    print("\nFetcher finished. Inspect the saved HTML before writing/running a parser.")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())

