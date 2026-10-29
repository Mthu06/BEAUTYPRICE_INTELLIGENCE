"""Fetch Watsons Vietnam body-wash listing HTML using the site's rendered pager.

Run from project root:
    python src/parsers/fetch_watsons_sua_tam.py --start-page 2 --end-page 5 --timeout 60 --delay 3

Navigation starts at page 1 and advances with the visible right-arrow control,
then saves only the requested pages. This matches the supplied Watsons HTML,
where pagination arrows are anchors without href attributes. HTML only: no
product-detail visits, review-text collection, parsing, or catalog updates.
"""
from __future__ import annotations

import argparse
import re
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

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "watsons" / "html" / "sua_tam"
BASE_URL = (
    "https://www.watsons.vn/vi/ch%C4%83m-s%C3%B3c-c%C3%A1-nh%C3%A2n/"
    "s%E1%BB%AFa-gel-t%E1%BA%AFm/c/0403001?currentPage=0"
)
CARD_SELECTOR = "e2-product-tile"
PAGINATION_SELECTOR = ".e2-pagination"
TOTAL_PAGES = 5
PRODUCT_ID_RE = re.compile(r"/p/(BP_[A-Za-z0-9_-]+)", re.I)
MAINTENANCE_MARKERS = (
    "maintenance", "đang nâng cấp hệ thống", "chúng tôi đang nâng cấp",
)
CHALLENGE_MARKERS = (
    "verify you are human", "are you a robot", "captcha", "access denied",
    "unusual traffic", "security verification", "checking your browser",
    "xác minh bạn không phải", "truy cập bị từ chối",
)


def detect_unavailable_page(driver) -> str | None:
    title = (driver.title or "").lower()
    html = (driver.page_source or "").lower()[:300_000]
    url = (driver.current_url or "").lower()
    if "maintenance.html" in url or any(x in title or x in html for x in MAINTENANCE_MARKERS):
        return "maintenance"
    if any(x in title or x in html for x in CHALLENGE_MARKERS):
        return "challenge/verification"
    if "0403001" not in url:
        return f"unexpected redirect ({driver.current_url})"
    return None


def current_page(driver) -> int | None:
    for selector in (
        ".e2-pagination .page-current",
        ".e2-pagination ul.pagination li.page-item.active a",
        ".e2-pagination .pagination li.active a",
    ):
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                value = (element.text or "").strip()
                if value.isdigit():
                    return int(value)
        except WebDriverException:
            pass
    # Fallback for the fractional pager in the supplied HTML, e.g. 2/5.
    try:
        for element in driver.find_elements(By.CSS_SELECTOR, PAGINATION_SELECTOR):
            match = re.search(r"(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)", element.text or "")
            if match:
                return int(match.group(1))
    except WebDriverException:
        pass
    return None


def total_pages(driver) -> int | None:
    try:
        for element in driver.find_elements(By.CSS_SELECTOR, ".e2-pagination .page-total"):
            value = (element.text or "").strip()
            if value.isdigit():
                return int(value)
        for element in driver.find_elements(By.CSS_SELECTOR, PAGINATION_SELECTOR):
            match = re.search(r"(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)", element.text or "")
            if match:
                return int(match.group(2))
    except WebDriverException:
        pass
    return None


def product_ids(driver) -> list[str]:
    found: list[str] = []
    for card in driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR):
        try:
            for link in card.find_elements(By.CSS_SELECTOR, "a[href*='/p/BP_']"):
                match = PRODUCT_ID_RE.search(link.get_attribute("href") or "")
                if match:
                    found.append(match.group(1).upper())
                    break
        except WebDriverException:
            continue
    return found


def wait_for_page(driver, expected: int, timeout: int) -> list[str]:
    deadline = time.monotonic() + timeout
    last = "DOM chưa ổn định"
    previous: tuple[str, ...] | None = None
    stable = 0
    while time.monotonic() < deadline:
        block = detect_unavailable_page(driver)
        if block:
            raise RuntimeError(f"Watsons đang hiển thị {block}; dừng và không lưu trang này.")
        active = current_page(driver)
        total = total_pages(driver)
        ids = product_ids(driver)
        cards = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)
        if active != expected:
            last = f"pagination={active}, cần {expected}; URL={driver.current_url!r}"
        elif total is not None and total != TOTAL_PAGES:
            last = f"website hiển thị {total} trang, cần {TOTAL_PAGES}"
        elif not cards or not ids:
            last = f"cards={len(cards)}, IDs={len(ids)}"
        else:
            signature = tuple(ids)
            stable = stable + 1 if signature == previous else 0
            previous = signature
            if stable >= 2:
                if len(ids) != len(set(ids)):
                    raise RuntimeError(f"Trang {expected} có ID trùng trong cùng trang.")
                return ids
        time.sleep(0.8)
    raise TimeoutException(f"Không xác nhận được trang {expected} sau {timeout}s: {last}; title={driver.title!r}; URL={driver.current_url!r}")


def next_control(driver):
    # In the supplied HTML the arrow anchors have no href; the last enabled
    # .page-item is the right-arrow control.
    for pager in driver.find_elements(By.CSS_SELECTOR, PAGINATION_SELECTOR):
        items = pager.find_elements(By.CSS_SELECTOR, "ul.pagination li.page-item")
        for item in reversed(items):
            try:
                classes = (item.get_attribute("class") or "").lower()
                if "disabled" in classes:
                    continue
                anchors = item.find_elements(By.CSS_SELECTOR, "a.page-link")
                if not anchors:
                    continue
                anchor = anchors[0]
                icon_classes = " ".join(
                    (el.get_attribute("class") or "")
                    for el in anchor.find_elements(By.CSS_SELECTOR, "i")
                ).lower()
                label = " ".join([
                    (anchor.get_attribute("aria-label") or ""),
                    (anchor.get_attribute("title") or ""),
                    (anchor.text or ""), icon_classes,
                ]).lower()
                if "arrow-right" in label or "next" in label or "tiếp" in label:
                    return anchor
            except (StaleElementReferenceException, WebDriverException):
                continue
    return None


def advance_page(driver, expected: int, timeout: int) -> list[str]:
    old_ids = tuple(product_ids(driver))
    button = next_control(driver)
    if button is None:
        raise RuntimeError("Không tìm thấy nút trang kế tiếp đang bật; dừng, không tự chuyển URL trực tiếp.")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    time.sleep(0.3)
    try:
        button.click()
    except ElementClickInterceptedException:
        # Use DOM click only on the site's visible pagination control.
        driver.execute_script("arguments[0].click();", button)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        block = detect_unavailable_page(driver)
        if block:
            raise RuntimeError(f"Sau khi bấm phân trang, Watsons chuyển sang {block}; dừng.")
        if current_page(driver) == expected:
            return wait_for_page(driver, expected, max(10, int(deadline - time.monotonic())))
        # If the counter is temporarily absent, wait for the product IDs to change.
        ids_now = tuple(product_ids(driver))
        if current_page(driver) is None and ids_now and ids_now != old_ids:
            return wait_for_page(driver, expected, max(10, int(deadline - time.monotonic())))
        time.sleep(0.5)
    raise TimeoutException(f"Bấm sang trang {expected} nhưng phân trang không xác nhận được; URL={driver.current_url!r}")


def save_page(driver, page: int, ids: list[str], overwrite: bool) -> None:
    if current_page(driver) != page:
        raise RuntimeError(f"Từ chối lưu: pager hiển thị {current_page(driver)}, cần {page}.")
    if total_pages(driver) not in (None, TOTAL_PAGES):
        raise RuntimeError(f"Từ chối lưu: số trang hiển thị không phải {TOTAL_PAGES}.")
    path = OUT_DIR / f"watsons_sua_tam_page_{page}.html"
    if path.exists() and not overwrite:
        print(f"  SKIP save: {path.name} đã tồn tại; giữ nguyên file cũ.")
        return
    html = driver.page_source or ""
    if len(html) < 10_000:
        raise RuntimeError(f"Từ chối lưu HTML quá ngắn: {len(html)} ký tự.")
    path.write_text(html, encoding="utf-8")
    print(f"  Title: {driver.title!r}")
    print(f"  URL: {driver.current_url}")
    print(f"  Pagination: {page}/{total_pages(driver) or '?'}")
    print(f"  Product tiles: {len(driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR))}")
    print(f"  Product IDs: {len(ids)} ({len(set(ids))} unique)")
    print(f"  Saved: {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Fetch Watsons Vietnam body-wash category HTML through rendered pagination.")
    ap.add_argument("--start-page", type=int, default=1, help="First page to save (1-5); navigation still starts at page 1")
    ap.add_argument("--end-page", type=int, default=5, help="Last page to save (1-5)")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--overwrite", action="store_true", help="Replace existing HTML files only when explicitly intended")
    args = ap.parse_args()
    if not (1 <= args.start_page <= TOTAL_PAGES and 1 <= args.end_page <= TOTAL_PAGES):
        ap.error("--start-page and --end-page must be between 1 and 5")
    if args.start_page > args.end_page:
        ap.error("--start-page must be <= --end-page")
    if args.timeout < 10 or args.delay < 1:
        ap.error("--timeout must be >= 10 and --delay must be >= 1")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    options = Options()
    if args.headless:
        options.add_argument("--headless=new")
    options.page_load_strategy = "eager"
    options.add_argument("--window-size=1440,1100")
    options.add_argument("--lang=vi-VN")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)  # clean Selenium-managed session; no custom profile
        driver.set_page_load_timeout(args.timeout)
        print("WATSONS SỮA TẮM FETCH — RENDERED PAGINATION")
        print(f"Pages to save: {args.start_page}-{args.end_page} of {TOTAL_PAGES}")
        print("Navigation starts at page 1 and uses the visible right-arrow; HTML only.\n")
        try:
            driver.get(BASE_URL)
        except TimeoutException:
            print("Page-load timeout; checking whether the listing rendered.")
        ids = wait_for_page(driver, 1, args.timeout)
        print(f"Opened page 1: {len(ids)} product IDs verified.")
        if args.start_page == 1:
            save_page(driver, 1, ids, args.overwrite)
        for page in range(2, args.end_page + 1):
            time.sleep(args.delay)
            ids = advance_page(driver, page, args.timeout)
            print(f"Reached page {page}: {len(ids)} product IDs verified.")
            if page >= args.start_page:
                save_page(driver, page, ids, args.overwrite)
            previous_path = OUT_DIR / f"watsons_sua_tam_page_{page - 1}.html"
            if page >= args.start_page and previous_path.exists():
                previous = set(PRODUCT_ID_RE.findall(previous_path.read_text(encoding="utf-8", errors="replace")))
                overlap = previous.intersection(ids)
                print(f"  Overlap with previous saved HTML: {len(overlap)}")
                if overlap:
                    print("  WARNING: IDs repeat across adjacent pages; review before parsing.")
        print("\nFetch finished. Validate saved HTML before running any parser.")
        return 0
    except (TimeoutException, RuntimeError, WebDriverException) as exc:
        print(f"STOP: {type(exc).__name__}: {exc}")
        if driver is not None:
            print(f"Current title: {driver.title!r}")
            print(f"Current URL: {driver.current_url!r}")
            diag = OUT_DIR / "watsons_sua_tam_diagnostic.html"
            html = driver.page_source or ""
            if len(html) > 10_000 and not diag.exists():
                diag.write_text(html, encoding="utf-8")
                print(f"Diagnostic saved without overwriting: {diag}")
        print("Stopped without saving the failed page as product data. Do not retry repeatedly if maintenance/challenge appears.")
        return 1
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())

