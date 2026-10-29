"""Fetch Watsons Vietnam sunscreen listing HTML for pages 1 through 22.

Run from project root:
    python src/parsers/fetch_watsons_sunscreens.py --timeout 60 --delay 3

This script ONLY saves rendered listing HTML. It does not parse products, visit
product-detail pages, collect review text, update snapshots, or rebuild catalog.
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "watsons" / "html" / "kem_chong_nang"
PROFILE_DIR = ROOT / "data" / "raw" / "watsons" / "chrome_profile"
BASE_URL = (
    "https://www.watsons.vn/vi/search?"
    "text=ch%E1%BB%91ng%20n%E1%BA%AFng&useDefaultSearch=false&brandRedirect=true&currentPage=0"
)
CARD_SELECTOR = "e2-product-tile"
PRODUCT_ID_RE = re.compile(r"/p/(BP_[A-Za-z0-9_-]+)", re.I)
BLOCK_MARKERS = (
    "verify you are human", "are you a robot", "captcha", "access denied",
    "unusual traffic", "security verification", "checking your browser",
    "xác minh bạn không phải", "truy cập bị từ chối",
)


def page_url(page_index: int) -> str:
    """Watsons uses zero-based currentPage: page 1=0, page 2=1."""
    parsed = urlparse(BASE_URL)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["currentPage"] = [str(page_index)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def current_page_index(url: str) -> int | None:
    try:
        values = parse_qs(urlparse(url).query).get("currentPage")
        return int(values[0]) if values else None
    except (ValueError, IndexError):
        return None


def get_ids(driver) -> list[str]:
    ids: list[str] = []
    for card in driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR):
        try:
            for link in card.find_elements(By.CSS_SELECTOR, "a[href*='/p/BP_']"):
                match = PRODUCT_ID_RE.search(link.get_attribute("href") or "")
                if match:
                    ids.append(match.group(1).upper())
                    break
        except WebDriverException:
            continue
    return ids


def active_pagination_number(driver) -> int | None:
    selectors = (
        ".e2-pagination ul.pagination li.page-item.active",
        ".e2-pagination .pagination li.active",
    )
    for selector in selectors:
        try:
            for item in driver.find_elements(By.CSS_SELECTOR, selector):
                text = (item.text or "").strip()
                if text.isdigit():
                    return int(text)
        except WebDriverException:
            pass
    return None


def check_for_challenge(driver) -> None:
    title = driver.title or ""
    html = driver.page_source or ""
    body = ""
    try:
        body = driver.find_element(By.TAG_NAME, "body").text or ""
    except WebDriverException:
        pass
    sample = f"{title}\n{html[:120000]}\n{body}".lower()
    if any(marker in sample for marker in BLOCK_MARKERS):
        raise RuntimeError("Có dấu hiệu trang xác minh/chặn truy cập; dừng, không tìm cách vượt chặn.")


def wait_for_expected_page(driver, page_number: int, timeout: int) -> list[str]:
    expected_index = page_number - 1
    deadline = time.monotonic() + timeout
    previous_signature = None
    stable_rounds = 0
    last_note = "chưa có DOM sản phẩm ổn định"

    while time.monotonic() < deadline:
        check_for_challenge(driver)
        url = driver.current_url or ""
        index = current_page_index(url)
        active_number = active_pagination_number(driver)
        cards = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)
        ids = get_ids(driver)

        # Do not save a listing unless URL and rendered pagination agree.
        if index != expected_index:
            last_note = f"URL currentPage={index}, cần {expected_index}; URL={url}"
            time.sleep(0.8)
            continue
        if active_number != page_number:
            last_note = f"pagination active={active_number}, cần {page_number}"
            time.sleep(0.8)
            continue
        if len(cards) < 1 or len(ids) < 1:
            last_note = f"cards={len(cards)}, IDs={len(ids)}"
            time.sleep(0.8)
            continue

        signature = tuple(ids)
        if signature == previous_signature:
            stable_rounds += 1
        else:
            stable_rounds = 0
        previous_signature = signature
        if stable_rounds >= 2:
            if len(ids) != len(set(ids)):
                raise RuntimeError(f"Trang {page_number}: có ID trùng ngay trong cùng trang ({len(ids)} IDs).")
            return ids
        time.sleep(0.8)

    raise TimeoutException(
        f"Không xác nhận được trang {page_number} sau {timeout}s: {last_note}; "
        f"title={driver.title!r}; URL={driver.current_url!r}"
    )


def save_page(driver, page_number: int, ids: list[str]) -> set[str]:
    url = driver.current_url or ""
    expected_index = page_number - 1
    if current_page_index(url) != expected_index:
        raise RuntimeError(f"Từ chối lưu trang {page_number}: URL không đúng chỉ số 0-based: {url}")
    active = active_pagination_number(driver)
    if active != page_number:
        raise RuntimeError(f"Từ chối lưu trang {page_number}: website đang đánh dấu page {active}.")

    html = driver.page_source or ""
    if len(html) < 10_000:
        raise RuntimeError(f"Từ chối lưu HTML quá ngắn ({len(html)} bytes).")

    path = OUT_DIR / f"watsons_sunscreens_page_{page_number}.html"
    path.write_text(html, encoding="utf-8")
    print(f"  Title: {driver.title!r}")
    print(f"  URL: {url}")
    print(f"  Pagination active: {active}")
    print(f"  Cards: {len(driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR))}")
    print(f"  IDs: {len(ids)} ({len(set(ids))} unique)")
    print(f"  Saved: {path}")
    return set(ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Watsons sunscreen listing HTML (pages 1-22).")
    parser.add_argument("--delay", type=float, default=3.0, help="Pause between pages, in seconds")
    parser.add_argument("--timeout", type=int, default=60, help="Wait timeout per page, in seconds")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headlessly")
    parser.add_argument("--start-page", type=int, default=1, help="First displayed page to fetch (1-22)")
    parser.add_argument("--end-page", type=int, default=22, help="Last displayed page to fetch (1-22)")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing HTML files in the selected range")
    parser.add_argument("--fresh-profile", action="store_true", help="Use a temporary Chrome profile")
    args = parser.parse_args()
    if args.delay < 1:
        parser.error("--delay must be >= 1 second")
    if args.timeout < 10:
        parser.error("--timeout must be >= 10 seconds")
    if not (1 <= args.start_page <= 22) or not (1 <= args.end_page <= 22):
        parser.error("--start-page and --end-page must be between 1 and 22")
    if args.start_page > args.end_page:
        parser.error("--start-page must be <= --end-page")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    options = Options()
    if args.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1100")
    options.add_argument("--lang=vi-VN")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    if args.fresh_profile:
        profile = OUT_DIR / "temporary_chrome_profile"
        profile.mkdir(parents=True, exist_ok=True)
        print(f"Using temporary profile: {profile}")
    else:
        profile = PROFILE_DIR
        print(f"Using persistent profile: {profile}")
    options.add_argument(f"--user-data-dir={profile}")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(args.timeout)
        total_pages = 22
        start_page = args.start_page
        end_page = args.end_page
        print("\nWATSONS SUNSCREEN FETCH — DIRECT PAGE URLS / RESUMABLE")
        print(f"HTML only | requested pages {start_page}-{end_page} | currentPage={start_page - 1}-{end_page - 1}")
        print("No product-detail visits, parsing, snapshots, or catalog updates\n")

        all_ids: dict[int, set[str]] = {}
        for page_number in range(start_page, end_page + 1):
            output_path = OUT_DIR / f"watsons_sunscreens_page_{page_number}.html"
            if output_path.exists() and not args.overwrite:
                print(f"\nERROR: {output_path.name} already exists. Refusing to overwrite it.")
                print("Choose a later --start-page or add --overwrite only if you intentionally want to replace existing HTML.")
                return 1
            url = page_url(page_number - 1)
            print(f"[{page_number}/{total_pages}] Opening page {page_number}: {url}")
            try:
                driver.get(url)
            except TimeoutException:
                print("  Navigation timed out; checking rendered page anyway.")
            time.sleep(args.delay)
            try:
                ids = wait_for_expected_page(driver, page_number, args.timeout)
                ids_set = save_page(driver, page_number, ids)
                all_ids[page_number] = ids_set
                if page_number > 1:
                    previous_ids = all_ids.get(page_number - 1)
                    if previous_ids is None:
                        previous_path = OUT_DIR / f"watsons_sunscreens_page_{page_number - 1}.html"
                        if previous_path.exists():
                            try:
                                from bs4 import BeautifulSoup
                                previous_soup = BeautifulSoup(previous_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
                                previous_ids = set()
                                for link in previous_soup.select('e2-product-tile a[href*="/p/BP_"]'):
                                    match = PRODUCT_ID_RE.search(link.get("href", ""))
                                    if match:
                                        previous_ids.add(match.group(1).upper())
                            except Exception:
                                previous_ids = None
                    if previous_ids is not None:
                        overlap_prev = previous_ids & ids_set
                        print(f"  Overlap with previous page: {len(overlap_prev)}")
                        if overlap_prev:
                            print("  WARNING: overlap detected; HTML saved, but review this page before parsing.")
                    else:
                        print("  Overlap with previous page: not checked (previous HTML unavailable or unreadable)")
            except (TimeoutException, RuntimeError, WebDriverException) as exc:
                print(f"  ERROR: page {page_number} not confirmed: {type(exc).__name__}: {exc}")
                print(f"  Current URL: {driver.current_url!r}")
                print(f"  Current title: {driver.title!r}")
                print(f"  Active pagination: {active_pagination_number(driver)}")
                print(f"  Cards: {len(driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR))}")
                diagnostic_path = OUT_DIR / f"watsons_sunscreens_page_{page_number}_diagnostic.html"
                html = driver.page_source or ""
                if len(html) > 10_000:
                    diagnostic_path.write_text(html, encoding="utf-8")
                    print(f"  Diagnostic HTML saved: {diagnostic_path}")
                print(f"Stopped at page {page_number}; previously saved HTML remains untouched. Rerun with --start-page {page_number} --end-page {end_page} to resume here.")
                return 1
            if page_number < total_pages:
                time.sleep(args.delay)

        all_product_ids = set().union(*all_ids.values()) if all_ids else set()
        total_page_id_count = sum(len(ids) for ids in all_ids.values())
        duplicate_count = total_page_id_count - len(all_product_ids)
        print("\nFETCH SUMMARY")
        print(f"Pages saved in this run: {len(all_ids)}/{end_page - start_page + 1}")
        for page_number, ids in all_ids.items():
            print(f"Page {page_number} unique IDs: {len(ids)}")
        print(f"Total page-level IDs: {total_page_id_count}")
        print(f"Unique IDs across all pages: {len(all_product_ids)}")
        print(f"Repeated IDs across pages (counted beyond first occurrence): {duplicate_count}")
        if duplicate_count:
            print("WARNING: repeated IDs detected across pages; review before parsing.")
        else:
            print(f"No repeated product IDs among the pages checked in this run ({start_page}-{end_page}).")
        print("Next step: inspect/parse only after confirming these HTML files are correct.")
        return 0
    except WebDriverException as exc:
        print(f"Chrome/Selenium error: {type(exc).__name__}: {exc}")
        return 2
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())

