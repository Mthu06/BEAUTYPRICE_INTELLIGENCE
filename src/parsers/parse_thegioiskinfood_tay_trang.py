"""Parse saved The Gioi SkinFood makeup-remover collection HTML and create product + QA datasets.

Run from project root:
    python src/parsers/parse_thegioiskinfood_tay_trang.py

Input:
    data/raw/thegioiskinfood/html/tay_trang/thegioiskinfood_tay_trang_page_*.html

Outputs:
    data/interim/thegioiskinfood/thegioiskinfood_tay_trang.csv
    data/interim/thegioiskinfood/thegioiskinfood_tay_trang_qa.csv
    data/interim/thegioiskinfood/thegioiskinfood_tay_trang_rejected_cards.csv
    data/interim/thegioiskinfood/thegioiskinfood_tay_trang_qa_report.csv
    data/interim/thegioiskinfood/thegioiskinfood_tay_trang_qa_issues.csv

This parser only reads saved collection HTML. It does not visit product pages,
collect review text, or modify price_snapshots.csv.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HTML_DIR = ROOT / "data" / "raw" / "thegioiskinfood" / "html" / "tay_trang"
OUT_DIR = ROOT / "data" / "interim" / "thegioiskinfood"
OUT_CSV = OUT_DIR / "thegioiskinfood_tay_trang.csv"
QA_CSV = OUT_DIR / "thegioiskinfood_tay_trang_qa.csv"
REJECTED_CSV = OUT_DIR / "thegioiskinfood_tay_trang_rejected_cards.csv"
QA_REPORT_CSV = OUT_DIR / "thegioiskinfood_tay_trang_qa_report.csv"
QA_ISSUES_CSV = OUT_DIR / "thegioiskinfood_tay_trang_qa_issues.csv"

BASE_URL = "https://thegioiskinfood.com"
CATEGORY = "tay_trang"

FIELDS = [
    "source", "category", "product_id", "sku", "product_name", "brand",
    "current_price_vnd", "current_price_max_vnd", "listed_price_vnd", "listed_price_max_vnd",
    "discount_percent", "rating", "rating_percent", "review_count", "sold_count_text",
    "product_url", "image_url", "collected_at", "source_file",
]
QA_FIELDS = FIELDS + [
    "qa_missing_product_id", "qa_missing_product_name", "qa_missing_brand",
    "qa_missing_product_url", "qa_missing_current_price", "qa_invalid_current_price",
    "qa_missing_listed_price", "qa_invalid_listed_price",
    "qa_missing_discount_percent", "qa_invalid_discount_percent",
    "qa_missing_rating", "qa_invalid_rating", "qa_missing_rating_percent",
    "qa_invalid_rating_percent", "qa_missing_review_count", "qa_invalid_review_count",
    "qa_missing_collected_at", "qa_duplicate_product_url", "qa_price_above_listed_price",
]


def get_text(element) -> str:
    return element.get_text(" ", strip=True) if element else ""


def missing(value: Any) -> bool:
    try:
        return value is None or bool(pd.isna(value)) or str(value).strip() == ""
    except (TypeError, ValueError):
        return value is None


def parse_money_values(value: str | None) -> list[int]:
    """Extract positive VND amounts; ignore zero placeholders in price ranges."""
    if not value:
        return []
    matches = re.findall(r"\d[\d.,]*", str(value).replace("\xa0", " "))
    values = []
    for match in matches:
        digits = re.sub(r"\D", "", match)
        if digits:
            amount = int(digits)
            if amount > 0:
                values.append(amount)
    return values


def parse_float(value: str | None):
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return float(match.group(0).replace(",", ".")) if match else None


def parse_int(value: str | None):
    if not value:
        return None
    match = re.search(r"\d[\d.,]*", value)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    return int(digits) if digits else None


def normalize_product_url(href: str | None) -> str | None:
    if not href:
        return None
    parsed = urlparse(urljoin(BASE_URL, href.strip()))
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() not in {"thegioiskinfood.com", "www.thegioiskinfood.com"}:
        return None
    if not parsed.path.startswith("/products/"):
        return None
    return f"{BASE_URL}{parsed.path}".rstrip("/")


def card_candidates(soup: BeautifulSoup):
    cards = soup.select(".collection-itemloop .proLoop")
    return cards if cards else soup.select(".proLoop")


def parse_card(card, source_file: str, collected_at: str):
    name_link = card.select_one(".productName a[href*='/products/']")
    image_link = card.select_one(".productImg a[href*='/products/']")
    link = name_link or image_link
    if link is None:
        return None, "missing_product_link"

    product_url = normalize_product_url(link.get("href"))
    if not product_url:
        return None, "invalid_product_url_or_domain"

    product_name = get_text(name_link) or (link.get("title") or "").strip()
    if not product_name:
        image = card.select_one(".productImg img[alt]")
        product_name = (image.get("alt") or "").strip() if image else ""
    product_name = re.sub(r"\s+", " ", product_name).strip()

    vendor_node = card.select_one(".loopvendor a[data-vendor]") or card.select_one(".loopvendor a")
    brand = get_text(vendor_node) or None

    price_box = card.select_one(".productPrice-wrap") or card
    listed_values = parse_money_values(get_text(price_box.select_one("del")))
    current_values = parse_money_values(get_text(price_box.select_one("b.productPriceDel")))
    listed_price = min(listed_values) if listed_values else None
    listed_price_max = max(listed_values) if listed_values else None
    current_price = min(current_values) if current_values else None
    current_price_max = max(current_values) if current_values else None

    if current_price is None:
        candidates = [
            node for node in price_box.select("b, strong, span")
            if parse_money_values(get_text(node))
            and ("₫" in get_text(node) or "đ" in get_text(node).lower())
            and node.name != "del"
        ]
        if candidates:
            vals = parse_money_values(get_text(candidates[0]))
            current_price, current_price_max = min(vals), max(vals)

    discount_node = price_box.select_one(".productSale")
    discount_percent = parse_float(get_text(discount_node))
    # Keep the website's displayed discount badge; a range-price badge may not equal
    # a calculation using the minimum/maximum endpoints.

    image_node = card.select_one(".productImg img")
    image_url = None
    if image_node:
        image_src = image_node.get("src") or image_node.get("data-src")
        if not image_src:
            source_node = card.select_one(".productImg source")
            image_src = (source_node.get("srcset") or source_node.get("data-srcset")) if source_node else None
        if image_src:
            image_url = urljoin(BASE_URL, image_src.strip())

    product_id = None
    review_widget = card.select_one("[data-product-id]")
    if review_widget:
        product_id = review_widget.get("data-product-id")
    favorite_button = card.select_one("button.js-favorites[data-id]")
    if not product_id and favorite_button:
        product_id = favorite_button.get("data-id")
    sku = None  # SKU is not exposed in the collection-card markup supplied.

    # The visible count (e.g. (1,005)) is more informative than the placeholder
    # data-number-of-reviews="0" sometimes rendered by the second review widget.
    review_count = None
    visible_review_count = card.select_one(".hrv-crv-star-total")
    if visible_review_count:
        review_count = parse_int(get_text(visible_review_count))
    if review_count is None:
        review_data = card.select_one(".wrap-inner[data-number-of-reviews]")
        if review_data:
            parsed_count = parse_int(review_data.get("data-number-of-reviews"))
            review_count = parsed_count if parsed_count and parsed_count > 0 else None

    rating = None
    review_data = card.select_one(".wrap-inner[data-average-rating]")
    if review_data:
        parsed_rating = parse_float(review_data.get("data-average-rating"))
        # A zero value appears as a placeholder even when the visible widget has reviews.
        rating = parsed_rating if parsed_rating and parsed_rating > 0 else None
    rating_percent = None  # Not available in this collection-card HTML.

    sold_node = card.select_one(".productLoop-sold-qtt strong")
    sold_count_text = get_text(sold_node) or None  # e.g. "2,6k"; kept as text, not guessed as exact count.

    if not product_name:
        return None, "missing_product_name"
    if current_price is None or current_price <= 0:
        return None, "missing_or_invalid_current_price"

    return {
        "source": "thegioiskinfood", "category": CATEGORY,
        "product_id": str(product_id) if product_id else None, "sku": sku,
        "product_name": product_name, "brand": brand,
        "current_price_vnd": current_price, "current_price_max_vnd": current_price_max,
        "listed_price_vnd": listed_price, "listed_price_max_vnd": listed_price_max,
        "discount_percent": discount_percent, "rating": rating,
        "rating_percent": rating_percent, "review_count": review_count,
        "sold_count_text": sold_count_text, "product_url": product_url,
        "image_url": image_url, "collected_at": collected_at, "source_file": source_file,
    }, None


def write_csv(path: Path, fields: list[str], rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse saved The Gioi SkinFood makeup-remover collection HTML.")
    parser.add_argument("--html-dir", type=Path, default=DEFAULT_HTML_DIR,
                        help="Optional input directory override, mainly for local testing.")
    args = parser.parse_args()
    html_dir = args.html_dir
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(html_dir.glob("thegioiskinfood_tay_trang_page_*.html"))
    if not files:
        print(f"No HTML files found: {html_dir / 'thegioiskinfood_tay_trang_page_*.html'}")
        print("Run fetch_thegioiskinfood_tay_trang.py first, or check HTML_DIR.")
        return 1

    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    by_url: dict[str, dict] = {}
    rejected: list[dict] = []
    reason_counts = Counter()
    total_cards = duplicate_cards = 0

    for file in files:
        soup = BeautifulSoup(file.read_text(encoding="utf-8", errors="replace"), "html.parser")
        cards = card_candidates(soup)
        total_cards += len(cards)
        print(f"{file.name}: found {len(cards)} candidate cards")
        if not cards:
            print("  WARNING: no .proLoop product cards recognized in this HTML.")
        for index, card in enumerate(cards, start=1):
            record, reason = parse_card(card, file.name, collected_at)
            if reason:
                reason_counts[reason] += 1
                first_link = card.select_one("a[href*='/products/']")
                rejected.append({
                    "source_file": file.name, "card_index": index, "reason": reason,
                    "product_url": normalize_product_url(first_link.get("href", "")) if first_link else "",
                    "card_text": get_text(card)[:1000],
                })
                continue
            key = record["product_url"]
            if key not in by_url:
                by_url[key] = record
            else:
                duplicate_cards += 1
                existing = by_url[key]
                for field, value in record.items():
                    if field == "collected_at":
                        continue
                    if missing(existing.get(field)) and not missing(value):
                        existing[field] = value
                if len(record["product_name"]) > len(existing["product_name"]):
                    existing["product_name"] = record["product_name"]

    raw_rows = list(by_url.values())
    write_csv(OUT_CSV, FIELDS, raw_rows)
    write_csv(REJECTED_CSV, ["source_file", "card_index", "reason", "product_url", "card_text"], rejected)

    df = pd.DataFrame(raw_rows, columns=FIELDS)
    if df.empty:
        qa_rows = []
        report_rows = [("html_files", len(files)), ("candidate_cards", total_cards),
                       ("unique_products", 0), ("duplicate_cards_skipped", duplicate_cards),
                       ("rejected_cards", len(rejected))]
    else:
        df["qa_missing_product_id"] = df["product_id"].map(missing)
        df["qa_missing_product_name"] = df["product_name"].map(missing)
        df["qa_missing_brand"] = df["brand"].map(missing)
        df["qa_missing_product_url"] = df["product_url"].map(missing)
        current = pd.to_numeric(df["current_price_vnd"], errors="coerce")
        current_max = pd.to_numeric(df["current_price_max_vnd"], errors="coerce")
        listed = pd.to_numeric(df["listed_price_vnd"], errors="coerce")
        listed_max = pd.to_numeric(df["listed_price_max_vnd"], errors="coerce")
        discount = pd.to_numeric(df["discount_percent"], errors="coerce")
        rating = pd.to_numeric(df["rating"], errors="coerce")
        rating_percent = pd.to_numeric(df["rating_percent"], errors="coerce")
        review_count = pd.to_numeric(df["review_count"], errors="coerce")
        df["qa_missing_current_price"] = current.isna()
        df["qa_invalid_current_price"] = current.notna() & current.le(0)
        df["qa_missing_listed_price"] = listed.isna()
        df["qa_invalid_listed_price"] = listed.notna() & listed.le(0)
        df["qa_missing_discount_percent"] = discount.isna()
        df["qa_invalid_discount_percent"] = discount.notna() & ((discount < 0) | (discount > 100))
        df["qa_missing_rating"] = rating.isna()
        df["qa_invalid_rating"] = rating.notna() & ((rating < 0) | (rating > 5))
        df["qa_missing_rating_percent"] = rating_percent.isna()
        df["qa_invalid_rating_percent"] = rating_percent.notna() & ((rating_percent < 0) | (rating_percent > 100))
        df["qa_missing_review_count"] = review_count.isna()
        df["qa_invalid_review_count"] = review_count.notna() & ((review_count < 0) | (review_count % 1 != 0))
        df["qa_missing_collected_at"] = df["collected_at"].map(missing)
        # For price ranges, compare the maximum current price against the maximum listed price.
        df["qa_price_above_listed_price"] = (
            current_max.notna() & listed_max.notna() & (current_max > listed_max)
        )
        normalized_urls = df["product_url"].map(lambda v: str(v).split("#", 1)[0].rstrip("/") if not missing(v) else None)
        df["qa_duplicate_product_url"] = normalized_urls.notna() & normalized_urls.duplicated(keep=False)
        qa_rows = df[QA_FIELDS].to_dict("records")
        flag_columns = [c for c in QA_FIELDS if c.startswith("qa_")]
        report_rows = [("html_files", len(files)), ("candidate_cards", total_cards),
                       ("unique_products", len(raw_rows)), ("unique_product_urls", int(normalized_urls.nunique(dropna=True))),
                       ("duplicate_cards_skipped", duplicate_cards), ("rejected_cards", len(rejected))]
        report_rows.extend((c.removeprefix("qa_"), int(df[c].fillna(False).astype(bool).sum())) for c in flag_columns)

    write_csv(QA_CSV, QA_FIELDS, qa_rows)
    pd.DataFrame(report_rows, columns=["metric", "value"]).to_csv(QA_REPORT_CSV, index=False, encoding="utf-8-sig")
    if not df.empty:
        flag_columns = [c for c in QA_FIELDS if c.startswith("qa_")]
        issues = df.loc[df[flag_columns].fillna(False).astype(bool).any(axis=1), QA_FIELDS].copy()
    else:
        issues = pd.DataFrame(columns=QA_FIELDS)
    issues.to_csv(QA_ISSUES_CSV, index=False, encoding="utf-8-sig")

    print("\nTHE GIOI SKINFOOD MAKEUP REMOVER PARSER + QA SUMMARY")
    print(f"HTML directory: {html_dir}")
    print(f"HTML files found: {len(files)}")
    print(f"Candidate cards: {total_cards}")
    print(f"Unique products: {len(raw_rows)}")
    print(f"Duplicate cards skipped: {duplicate_cards}")
    print(f"Rejected cards: {len(rejected)}")
    print(f"Rejection reasons: {dict(reason_counts)}")
    print(f"Products CSV: {OUT_CSV}")
    print(f"QA CSV: {QA_CSV}")
    print(f"Rejected cards CSV: {REJECTED_CSV}")
    print(f"QA report CSV: {QA_REPORT_CSV}")
    print(f"QA issues CSV: {QA_ISSUES_CSV}")
    print("Note: this script parses saved HTML and does not modify price_snapshots.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


