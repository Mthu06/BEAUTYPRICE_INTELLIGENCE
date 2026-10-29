"""
Parse Watsons Vietnam sunscreen collection-page HTML into product and QA CSVs.

Run from the project root:
    python src/parsers/parse_watsons_sunscreens.py

Input:
    data/raw/watsons/html/kem_chong_nang/watsons_sunscreens_page_1.html
    ...
Only canonical page_N filenames are used. Diagnostic files and duplicate
filename variants such as page_1(1).html are ignored to avoid mixing failed
Fetch attempts with the verified page sequence.

Outputs are written to data/interim/watsons/. This script does not visit product
detail pages, collect review text, update price_snapshots.csv, or rebuild the
catalog.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "data" / "raw" / "watsons" / "html" / "kem_chong_nang"
OUTPUT_DIR = ROOT / "data" / "interim" / "watsons"
BASE_URL = "https://www.watsons.vn"
RETAILER = "watsons"
CATEGORY = "sunscreens"
CARD_SELECTOR = "e2-product-tile"

FIELDS = [
    "product_id", "retailer", "category", "product_name", "brand",
    "product_url", "current_price", "listed_price", "discount_percent",
    "rating", "review_count", "collected_at",
]
QA_EXTRA_FIELDS = ["source_file", "source_card_index", "qa_flags", "qa_issue_count"]


def clean_text(node) -> str | None:
    if node is None:
        return None
    value = " ".join(node.get_text(" ", strip=True).split())
    return value or None


def parse_vnd(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def parse_review_count(card) -> int | None:
    text = clean_text(card.select_one(".reviewCount"))
    if not text:
        return None
    match = re.search(r"\(\s*([\d.,]+)\s*\)", text)
    if not match:
        return None
    try:
        return int(match.group(1).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def product_id_from_url(url: str | None) -> str | None:
    match = re.search(r"/p/(BP_[A-Za-z0-9_-]+)", url or "")
    return match.group(1) if match else None


def page_number_from_name(path: Path) -> int | None:
    match = re.fullmatch(r"watsons_sunscreens_page_(\d+)\.html", path.name)
    return int(match.group(1)) if match else None


def validate_page(html: str, path: Path, expected_page: int) -> tuple[bool, str]:
    """Check visible pagination and URL query when those markers are present."""
    soup = BeautifulSoup(html, "html.parser")
    current_node = soup.select_one(".e2-pagination .page-current, .pagination .page-current")
    total_node = soup.select_one(".e2-pagination .page-total, .pagination .page-total")
    current_text = clean_text(current_node)
    total_text = clean_text(total_node)

    if current_text and current_text.isdigit():
        if int(current_text) != expected_page:
            return False, f"pagination_current_is_{current_text}_expected_{expected_page}"
    if total_text and total_text.isdigit() and int(total_text) < expected_page:
        return False, f"pagination_total_{total_text}_below_expected_page"

    cards = soup.select(CARD_SELECTOR)
    if not cards:
        return False, "no_product_cards"
    return True, "ok"


def extract_card(card, collected_at: str) -> dict:
    link = card.select_one("h2.productName a[href]")
    if link is None:
        link = card.select_one('a[aria-label="product detail"][href*="/p/"]')

    href = (link.get("href") or "").strip() if link else ""
    product_url = urljoin(BASE_URL, href) if href else None
    brand = clean_text(card.select_one("span.product-brand"))
    product_name = clean_text(link)
    if product_name and brand and product_name.startswith(brand):
        product_name = product_name[len(brand):].strip()

    current_price = parse_vnd(clean_text(card.select_one(".productPrice .formatted-value")))
    listed_price = parse_vnd(clean_text(card.select_one(".productOriginalPrice del")))
    discount = None
    if current_price is not None and listed_price is not None and listed_price > 0 and current_price <= listed_price:
        discount = round((listed_price - current_price) / listed_price * 100, 2)

    return {
        "product_id": product_id_from_url(product_url),
        "retailer": RETAILER,
        "category": CATEGORY,
        "product_name": product_name,
        "brand": brand,
        "product_url": product_url,
        "current_price": current_price,
        "listed_price": listed_price,
        "discount_percent": discount,
        # Listing cards show star icons but no numeric rating.
        "rating": None,
        "review_count": parse_review_count(card),
        "collected_at": collected_at,
    }


def issue_flags(row: dict) -> list[str]:
    flags = []
    for field in ("product_id", "product_name", "brand", "product_url", "current_price"):
        if row.get(field) in (None, ""):
            flags.append(f"qa_missing_{field}")
    if row.get("current_price") is not None and row["current_price"] <= 0:
        flags.append("qa_invalid_current_price")
    if row.get("listed_price") is not None and row["listed_price"] <= 0:
        flags.append("qa_invalid_listed_price")
    if row.get("current_price") is not None and row.get("listed_price") is not None:
        if row["current_price"] > row["listed_price"]:
            flags.append("qa_current_price_above_listed_price")
    if row.get("review_count") == 0:
        flags.append("qa_review_count_zero_suspected_placeholder")
    if row.get("review_count") is None:
        flags.append("qa_review_count_missing")
    flags.append("qa_rating_not_available_in_listing_html")
    if row.get("listed_price") is None:
        flags.append("qa_missing_listed_price")
    return flags


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Exact canonical filenames only; deliberately ignore diagnostics and
    # suffix variants created by Windows when multiple files share a name.
    html_files = sorted(
        (p for p in INPUT_DIR.glob("watsons_sunscreens_page_*.html")
         if page_number_from_name(p) is not None),
        key=lambda p: page_number_from_name(p) or 0,
    )
    if not html_files:
        print(f"No canonical page HTML files found in: {INPUT_DIR}")
        return 1

    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    products_by_url: dict[str, dict] = {}
    rejected = []
    page_checks = []
    candidate_count = 0
    duplicate_count = 0
    invalid_pages = []

    for path in html_files:
        page_no = page_number_from_name(path)
        html = path.read_text(encoding="utf-8", errors="ignore")
        valid, reason = validate_page(html, path, page_no)
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(CARD_SELECTOR)
        if not valid:
            invalid_pages.append((path.name, reason))
            page_checks.append({"source_file": path.name, "expected_page": page_no,
                                "status": "skipped", "reason": reason,
                                "candidate_cards": len(cards)})
            print(f"SKIP {path.name}: {reason}")
            continue

        page_checks.append({"source_file": path.name, "expected_page": page_no,
                            "status": "parsed", "reason": "ok",
                            "candidate_cards": len(cards)})
        print(f"{path.name}: page {page_no} verified; {len(cards)} candidate cards")
        candidate_count += len(cards)

        for index, card in enumerate(cards, start=1):
            row = extract_card(card, collected_at)
            row["source_file"] = path.name
            row["source_card_index"] = index
            if not row["product_url"] or not row["product_name"]:
                rejected.append({
                    "source_file": path.name,
                    "source_card_index": index,
                    "product_name": row["product_name"],
                    "product_url": row["product_url"],
                    "reason": "missing_product_name_or_url",
                    "raw_card_text": clean_text(card),
                })
                continue
            key = row["product_url"].split("#", 1)[0]
            if key in products_by_url:
                duplicate_count += 1
            # Latest canonical page/card occurrence wins.
            products_by_url[key] = row

    products = list(products_by_url.values())
    products.sort(key=lambda r: (r["product_id"] or "", r["product_name"] or ""))

    qa_rows, issue_rows = [], []
    for row in products:
        flags = issue_flags(row)
        qa_row = {**row, "qa_flags": "|".join(flags), "qa_issue_count": len(flags)}
        qa_rows.append(qa_row)
        if flags:
            issue_rows.append(qa_row)

    main_path = OUTPUT_DIR / "watsons_sunscreens.csv"
    qa_path = OUTPUT_DIR / "watsons_sunscreens_qa.csv"
    rejected_path = OUTPUT_DIR / "watsons_sunscreens_rejected_cards.csv"
    report_path = OUTPUT_DIR / "watsons_sunscreens_qa_report.csv"
    issues_path = OUTPUT_DIR / "watsons_sunscreens_qa_issues.csv"
    pages_path = OUTPUT_DIR / "watsons_sunscreens_page_validation.csv"

    write_csv(main_path, products, FIELDS)
    write_csv(qa_path, qa_rows, FIELDS + QA_EXTRA_FIELDS)
    write_csv(rejected_path, rejected, [
        "source_file", "source_card_index", "product_name", "product_url", "reason", "raw_card_text"
    ])
    write_csv(issues_path, issue_rows, FIELDS + QA_EXTRA_FIELDS)
    write_csv(pages_path, page_checks, [
        "source_file", "expected_page", "status", "reason", "candidate_cards"
    ])

    metrics = [
        ("html_files_found", len(html_files)),
        ("valid_pages_parsed", sum(p["status"] == "parsed" for p in page_checks)),
        ("invalid_pages_skipped", len(invalid_pages)),
        ("candidate_cards_from_valid_pages", candidate_count),
        ("unique_products", len(products)),
        ("duplicate_cards_skipped_or_overwritten", duplicate_count),
        ("rejected_cards", len(rejected)),
        ("missing_product_id", sum(not r.get("product_id") for r in products)),
        ("missing_brand", sum(not r.get("brand") for r in products)),
        ("missing_current_price", sum(r.get("current_price") is None for r in products)),
        ("missing_listed_price", sum(r.get("listed_price") is None for r in products)),
        ("missing_numeric_rating", sum(r.get("rating") is None for r in products)),
        ("missing_review_count", sum(r.get("review_count") is None for r in products)),
        ("review_count_zero_suspected_placeholder", sum(r.get("review_count") == 0 for r in products)),
    ]
    write_csv(report_path, [{"metric": k, "value": v} for k, v in metrics], ["metric", "value"])

    print("\nWATSONS SUNSCREENS PARSER + QA SUMMARY")
    print(f"Canonical HTML files found: {len(html_files)}")
    print(f"Valid pages parsed: {sum(p['status'] == 'parsed' for p in page_checks)}")
    print(f"Invalid pages skipped: {len(invalid_pages)}")
    print(f"Candidate cards: {candidate_count}")
    print(f"Unique products: {len(products)}")
    print(f"Duplicate cards skipped/overwritten: {duplicate_count}")
    print(f"Rejected cards: {len(rejected)}")
    print(f"Products CSV: {main_path}")
    print(f"QA CSV: {qa_path}")
    print(f"Rejected cards CSV: {rejected_path}")
    print(f"QA report CSV: {report_path}")
    print(f"QA issues CSV: {issues_path}")
    print(f"Page validation CSV: {pages_path}")
    print("Rating stays blank: the listing HTML exposes star icons, not a numeric score.")
    print("Review count 0 is retained as observed and flagged as a possible placeholder.")
    print("No price_snapshots.csv update or catalog rebuild was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

