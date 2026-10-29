"""Fetch Watsons Vietnam facial-cleanser search listing HTML (pages 1-11).

Run from project root:
    python src/parsers/fetch_watsons_cleansers.py --timeout 60 --delay 3

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
OUT_DIR = ROOT / "data" / "raw" / "watsons" / "html" / "sua_rua_mat"
PROFILE_DIR = ROOT / "data" / "raw" / "watsons" / "chrome_profile"
BASE_URL = (
    "https://www.watsons.vn/vi/search?"
    "text=s%E1%BB%AFa%20r%E1%BB%ADa%20m%E1%BA%B7t&currentPage=0"
)
CARD_SELECTOR = "e2-product-tile"
PRODUCT_ID_RE = re.compile(r"/p/(BP_[A-Za-z0-9_-]+)", re.I)
TOTAL_PAGES = 11
BLOCK_MARKERS = (
    "verify you are human", "are you a robot", "captcha", "access denied",
    "unusual traffic", "security verification", "checking your browser",
    "xác minh bạn không phải", "truy cập bị từ chối",
)


def page_url(page_index: int) -> str:
    """Watsons uses zero-based currentPage: displayed page 1=0, page 2=1."""
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
            links = card.find_elements(By.CSS_SELECTOR, "a[href*='/p/BP_']")
            for link in links:
                match = PRODUCT_ID_RE.search(link.get_attribute("href") or "")
                if match:
                    ids.append(match.group(1).upper())
                    break
        except WebDriverException:
            continue
    return ids


def displayed_page_number(driver) -> int | None:
    # This Watsons listing uses span.page-current / span.page-total,
    # rather than always marking the active page with li.active.
    for selector in (
        ".e2-pagination .page-current",
        ".e2-pagination ul.pagination li.page-item.active",
        ".e2-pagination .pagination li.active",
    ):
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                value = (element.text or "").strip()
                if value.isdigit():
                    return int(value)
        except WebDriverException:
            pass
    return None


def displayed_total_pages(driver) -> int | None:
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, ".e2-pagination .page-total")
        for element in elements:
            value = (element.text or "").strip()
            if value.isdigit():
                return int(value)
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
        raise RuntimeError(
            "Có dấu hiệu trang xác minh/chặn truy cập; dừng, không tìm cách vượt chặn."
        )


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
        active_number = displayed_page_number(driver)
        total_pages = displayed_total_pages(driver)
        cards = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)
        ids = get_ids(driver)

        if index != expected_index:
            last_note = f"URL currentPage={index}, cần {expected_index}; URL={url}"
            time.sleep(0.8)
            continue
        if active_number != page_number:
            last_note = f"page-current={active_number}, cần {page_number}"
            time.sleep(0.8)
            continue
        if total_pages is not None and total_pages != TOTAL_PAGES:
            last_note = f"website hiển thị {total_pages} trang, script đang kỳ vọng {TOTAL_PAGES}"
            time.sleep(0.8)
            continue
        if not cards or not ids:
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
                raise RuntimeError(
                    f"Trang {page_number}: có ID trùng trong cùng trang "
                    f"({len(ids)} IDs, {len(set(ids))} duy nhất)."
                )
            return ids
        time.sleep(0.8)

    raise TimeoutException(
        f"Không xác nhận được trang {page_number} sau {timeout}s: {last_note}; "
        f"title={driver.title!r}; URL={driver.current_url!r}"
    )


def extract_ids_from_saved_html(path: Path) -> set[str] | None:
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
        return {match.upper() for match in PRODUCT_ID_RE.findall(html)}
    except OSError:
        return None


def save_page(driver, page_number: int, ids: list[str], overwrite: bool) -> set[str]:
    url = driver.current_url or ""
    if current_page_index(url) != page_number - 1:
        raise RuntimeError(f"Từ chối lưu trang {page_number}: URL không đúng currentPage: {url}")
    if displayed_page_number(driver) != page_number:
        raise RuntimeError(
            f"Từ chối lưu trang {page_number}: website đang hiển thị page "
            f"{displayed_page_number(driver)}."
        )

    path = OUT_DIR / f"watsons_cleansers_page_{page_number}.html"
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"{path.name} đã tồn tại; không ghi đè. Dùng --start-page/--end-page "
            "để chạy phần khác hoặc thêm --overwrite nếu thật sự muốn thay."
        )

    html = driver.page_source or ""
    if len(html) < 10_000:
        raise RuntimeError(f"Từ chối lưu HTML quá ngắn ({len(html)} bytes).")

    path.write_text(html, encoding="utf-8")
    print(f"  Title: {driver.title!r}")
    print(f"  URL: {url}")
    print(f"  Pagination: {page_number}/{displayed_total_pages(driver) or 'không đọc được'}")
    print(f"  Product tiles: {len(driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR))}")
    print(f"  Product IDs: {len(ids)} ({len(set(ids))} unique)")
    print(f"  Saved: {path}")
    return set(ids)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Watsons facial-cleanser listing HTML (pages 1-11)."
    )
    parser.add_argument("--delay", type=float, default=3.0, help="Pause between pages, seconds")
    parser.add_argument("--timeout", type=int, default=60, help="Wait timeout per page, seconds")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headlessly")
    parser.add_argument("--start-page", type=int, default=1, help="First displayed page (1-11)")
    parser.add_argument("--end-page", type=int, default=11, help="Last displayed page (1-11)")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Allow replacing existing HTML files in the selected range",
    )
    parser.add_argument(
        "--fresh-profile", action="store_true",
        help="Use a temporary Chrome profile instead of the persistent Watsons profile",
    )
    args = parser.parse_args()

    if args.delay < 1:
        parser.error("--delay must be >= 1 second")
    if args.timeout < 10:
        parser.error("--timeout must be >= 10 seconds")
    if not (1 <= args.start_page <= TOTAL_PAGES):
        parser.error(f"--start-page must be between 1 and {TOTAL_PAGES}")
    if not (1 <= args.end_page <= TOTAL_PAGES):
        parser.error(f"--end-page must be between 1 and {TOTAL_PAGES}")
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
        print("\nWATSONS CLEANSERS FETCH — DIRECT PAGE URLS / RESUMABLE")
        print(
            f"HTML only | requested pages {args.start_page}-{args.end_page} "
            f"| currentPage={args.start_page - 1}-{args.end_page - 1}"
        )
        print(
            "No product-detail visits, parsing, review-text collection, "
            "price snapshots, or catalog updates.\n"
        )

        all_ids: dict[int, set[str]] = {}
        for page_number in range(args.start_page, args.end_page + 1):
            output_path = OUT_DIR / f"watsons_cleansers_page_{page_number}.html"
            if output_path.exists() and not args.overwrite:
                print(f"\nERROR: {output_path.name} already exists. Refusing to overwrite.")
                print(
                    f"Rerun with a suitable --start-page/--end-page, or use --overwrite "
                    "only if you intentionally want to replace these HTML files."
                )
                return 1

            url = page_url(page_number - 1)
            print(f"[{page_number}/{TOTAL_PAGES}] Opening page {page_number}: {url}")
            try:
                driver.get(url)
            except TimeoutException:
                print("  Navigation timed out; checking the rendered page anyway.")
            time.sleep(args.delay)

            try:
                ids = wait_for_expected_page(driver, page_number, args.timeout)
                ids_set = save_page(driver, page_number, ids, args.overwrite)
                all_ids[page_number] = ids_set

                previous_ids = all_ids.get(page_number - 1)
                if previous_ids is None and page_number > args.start_page:
                    previous_path = OUT_DIR / f"watsons_cleansers_page_{page_number - 1}.html"
                    if previous_path.exists():
                        previous_ids = extract_ids_from_saved_html(previous_path)
                if page_number > 1:
                    if previous_ids is not None:
                        overlap = previous_ids & ids_set
                        print(f"  Overlap with previous page: {len(overlap)}")
                        if overlap:
                            print("  WARNING: repeated IDs across adjacent pages; review before parsing.")
                    else:
                        print("  Overlap with previous page: not checked (previous HTML unavailable).")

            except FileExistsError as exc:
                print(f"  ERROR: {exc}")
                return 1
            except (TimeoutException, RuntimeError, WebDriverException) as exc:
                print(
                    f"  ERROR: page {page_number} not confirmed: "
                    f"{type(exc).__name__}: {exc}"
                )
                print(f"  Current URL: {driver.current_url!r}")
                print(f"  Current title: {driver.title!r}")
                print(f"  Displayed page: {displayed_page_number(driver)}")
                print(f"  Total pages shown: {displayed_total_pages(driver)}")
                print(f"  Product tiles: {len(driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR))}")
                diagnostic_path = OUT_DIR / f"watsons_cleansers_page_{page_number}_diagnostic.html"
                html = driver.page_source or ""
                if len(html) > 10_000:
                    diagnostic_path.write_text(html, encoding="utf-8")
                    print(f"  Diagnostic HTML saved: {diagnostic_path}")
                print(
                    f"Stopped at page {page_number}; previously saved files remain untouched. "
                    f"To resume, rerun with --start-page {page_number} --end-page {args.end_page}."
                )
                return 1

            if page_number < args.end_page:
                time.sleep(args.delay)

        all_product_ids = set().union(*all_ids.values()) if all_ids else set()
        total_page_ids = sum(len(ids) for ids in all_ids.values())
        repeated_count = total_page_ids - len(all_product_ids)
        print("\nFETCH SUMMARY")
        print(f"Pages saved in this run: {len(all_ids)}/{args.end_page - args.start_page + 1}")
        for page_number, ids in all_ids.items():
            print(f"Page {page_number}: {len(ids)} unique IDs")
        print(f"Total page-level IDs: {total_page_ids}")
        print(f"Unique IDs across checked pages: {len(all_product_ids)}")
        print(f"Repeated IDs across checked pages: {repeated_count}")
        if repeated_count:
            print("WARNING: repeated IDs detected; review the HTML before parsing.")
        else:
            print("No repeated product IDs among the pages checked in this run.")
        print("Next step: validate the saved HTML before running a parser.")
        return 0

    except WebDriverException as exc:
        print(f"Chrome/Selenium error: {type(exc).__name__}: {exc}")
        return 2
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())

