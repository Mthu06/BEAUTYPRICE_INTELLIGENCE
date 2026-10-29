# Tạo script thu thập trang 1–12
"""
Fetch rendered Hasaki serum category pages using Selenium/Chrome.
Run from project root:
    python src/parsers/fetch_hasaki_serum.py

Requirements:
    pip install selenium beautifulsoup4

This uses the browser-rendered DOM because requests returned an HTML shell without product cards.
It does not bypass access controls. If the site presents a challenge or blocks access, stop.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = "https://hasaki.vn/danh-muc/serum-tinh-chat-c75.html?p=1"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "hasaki" / "html" / "serum"
PARSER = None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=9)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument("--parse-after-fetch", action="store_true")
    ap.add_argument("--headless", action="store_true",
                    help="Run Chrome headlessly; leave off initially so you can observe the browser.")
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
    saved, failed, total_cards = [], [], 0
    try:
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, args.timeout)
        print("HASAKI SERUM SELENIUM FETCH")
        print(f"Target pages: 1..{args.max_pages}")
        print(f"Output: {OUT_DIR}")
        print("A Chrome window will open. Do not interact with login/payment pages.")
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        for page in range(1, args.max_pages + 1):
            parts = urlsplit(BASE_URL)
            query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "p"]
            query.append(("p", str(page)))
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
            print(f"\n[{page}/{args.max_pages}] Opening {url}")
            try:
                driver.get(url)
                wait.until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))
                # Wait for rendered product anchors. If not present, still save the DOM for diagnosis.
                try:
                    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'a[href*="/san-pham/"]')) > 0)
                except TimeoutException:
                    pass

                title = driver.title or ""
                current_url = driver.current_url or ""
                page_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                if any(marker in page_text for marker in (
                    "verify you are human", "access denied", "unusual traffic", "captcha"
                )):
                    failed.append((page, "verification/block page; stopped"))
                    print("STOP: possible verification/block page. Respecting site access controls.")
                    break

                html = driver.page_source
                count = len(driver.find_elements(By.CSS_SELECTOR, 'a[href*="/san-pham/"]'))
                if "serum" not in (title + " " + current_url).lower():
                    failed.append((page, "unexpected title/URL"))
                    print(f"WARNING: title/URL not clearly serum category: {title}")
                if count == 0:
                    failed.append((page, "no rendered product links"))
                    print(f"WARNING: no product anchors found. Title: {title}")
                    # Save only for diagnosis, same filename convention; parser will report zero.
                out = OUT_DIR / f"serum_page_{page}.html"
                out.write_text(html, encoding="utf-8")
                saved.append(page)
                total_cards += count
                print(f"Saved {out.name} | title={title!r} | rendered product links={count}")
            except WebDriverException as exc:
                failed.append((page, f"browser error: {exc.__class__.__name__}: {exc}"))
                print(f"ERROR on page {page}: {exc.__class__.__name__}: {exc}")
            if page < args.max_pages:
                time.sleep(args.delay)

        print("\nFETCH SUMMARY")
        print(f"Pages saved: {len(saved)}/{args.max_pages}")
        print(f"Rendered product links counted (including duplicates): {total_cards}")
        if failed:
            print("Pages needing review:")
            for page, reason in failed:
                print(f" - page {page}: {reason}")

    except WebDriverException as exc:
        print("Could not start Chrome WebDriver.")
        print(f"Details: {exc}")
        print("Update Chrome, then run: pip install -U selenium")
        return 1
    finally:
        if driver is not None:
            driver.quit()

    if args.parse_after_fetch and saved:
        print("\nRunning parser...")
        result = subprocess.run([sys.executable, str(PARSER)], cwd=str(ROOT), check=False)
        if result.returncode:
            return result.returncode
    print("\nFetcher finished. Review summary before running the normalization pipeline.")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())


