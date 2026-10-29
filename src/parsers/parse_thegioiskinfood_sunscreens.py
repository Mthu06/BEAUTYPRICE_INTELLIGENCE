"""Parse saved The Gioi SkinFood sunscreen collection HTML and create product + QA datasets.

Run from project root:
    python src/parsers/parse_thegioiskinfood_sunscreens.py

Input:
    data/raw/thegioiskinfood/html/kem_chong_nang/
        thegioiskinfood_kem_chong_nang_page_*.html

Outputs:
    data/interim/thegioiskinfood/thegioiskinfood_sunscreens.csv
    data/interim/thegioiskinfood/thegioiskinfood_sunscreens_qa.csv
    data/interim/thegioiskinfood/thegioiskinfood_sunscreens_rejected_cards.csv
    data/interim/thegioiskinfood/thegioiskinfood_sunscreens_qa_report.csv
    data/interim/thegioiskinfood/thegioiskinfood_sunscreens_qa_issues.csv

This parser only reads saved collection HTML. It does not visit product pages,
collect review text, or modify price_snapshots.csv.
"""
from __future__ import annotations

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
HTML_DIR = ROOT / "data" / "raw" / "thegioiskinfood" / "html" / "kem_chong_nang"
OUT_DIR = ROOT / "data" / "interim" / "thegioiskinfood"
OUT_CSV = OUT_DIR / "thegioiskinfood_sunscreens.csv"
QA_CSV = OUT_DIR / "thegioiskinfood_sunscreens_qa.csv"
REJECTED_CSV = OUT_DIR / "thegioiskinfood_sunscreens_rejected_cards.csv"
QA_REPORT_CSV = OUT_DIR / "thegioiskinfood_sunscreens_qa_report.csv"
QA_ISSUES_CSV = OUT_DIR / "thegioiskinfood_sunscreens_qa_issues.csv"

BASE_URL = "https://thegioiskinfood.com"
CATEGORY = "kem_chong_nang"

FIELDS = [
    "source", "category", "product_id", "sku", "product_name", "brand",
    "current_price_vnd", "current_price_max_vnd", "listed_price_vnd", "listed_price_max_vnd",
    "discount_percent", "rating", "rating_percent", "review_count", "product_url", "image_url",
    "collected_at", "source_file",
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
    """Return each amount in text such as '216,000₫ - 336,000₫'."""
    if not value:
        return []
    text = str(value).replace("\xa0", " ")
    matches = re.findall(r"\d[\d.,]*", text)
    values = []
    for match in matches:
        digits = re.sub(r"\D", "", match)
        if digits:
            values.append(int(digits))
    return values


def parse_money(value: str | None):
    """Return the first amount, useful for single-price and range-price fields."""
    values = parse_money_values(value)
    return values[0] if values else None


def parse_float(value: str | None):
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return float(match.group(0).replace(",", ".")) if match else None


def parse_int(value: str | None):
    match = re.search(r"\d[\d.,]*", value or "")
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
    # Product identity is based on the canonical path; remove query and fragment.
    return f"{BASE_URL}{parsed.path}".rstrip("/")


def card_candidates(soup: BeautifulSoup):
    """Use the site's product-card wrapper, not every product link inside it."""
    cards = soup.select(".collection-itemloop .proLoop")
    if cards:
        return cards
    # Fallback for saved HTML where collection-itemloop wrapper is absent.
    return soup.select(".proLoop")


def parse_card(card, source_file: str, collected_at: str):
    name_link = card.select_one(".productName a[href*='/products/']")
    image_link = card.select_one(".productImg a[href*='/products/']")
    link = name_link or image_link
    if link is None:
        return None, "missing_product_link"

    product_url = normalize_product_url(link.get("href"))
    if not product_url:
        return None, "invalid_product_url_or_domain"

    product_name = get_text(name_link)
    if not product_name:
        product_name = (link.get("title") or "").strip()
    if not product_name:
        image = card.select_one(".productImg img[alt]")
        product_name = (image.get("alt") or "").strip() if image else ""
    product_name = re.sub(r"\s+", " ", product_name).strip()

    vendor_node = card.select_one(".loopvendor a[data-vendor]") or card.select_one(".loopvendor a")
    brand = get_text(vendor_node) or None

    # The site's card uses <del> for listed price and .productPriceDel for current price.
    price_box = card.select_one(".productPrice-wrap") or card
    listed_node = price_box.select_one("del")
    current_node = price_box.select_one("b.productPriceDel")
    listed_values = parse_money_values(get_text(listed_node))
    current_values = parse_money_values(get_text(current_node))
    listed_price = listed_values[0] if listed_values else None
    listed_price_max = listed_values[-1] if listed_values else None
    current_price = current_values[0] if current_values else None
    current_price_max = current_values[-1] if current_values else None

    # Fallbacks for cards with a different price markup.
    if current_price is None:
        current_candidates = [
            node for node in price_box.select("b, strong, span")
            if parse_money(get_text(node)) is not None
            and ("₫" in get_text(node) or "đ" in get_text(node).lower())
            and node.name != "del"
        ]
        if current_candidates:
            fallback_values = parse_money_values(get_text(current_candidates[0]))
            current_price = fallback_values[0] if fallback_values else None
            current_price_max = fallback_values[-1] if fallback_values else None

    discount_node = price_box.select_one(".productSale")
    discount_percent = parse_float(get_text(discount_node))
    if discount_percent is None and listed_price and current_price is not None and listed_price >= current_price > 0:
        discount_percent = round((listed_price - current_price) / listed_price * 100, 2)

    image_node = card.select_one(".productImg img")
    image_url = None
    if image_node:
        image_src = image_node.get("src") or image_node.get("data-src")
        if not image_src:
            source_node = card.select_one(".productImg source")
            image_src = (source_node.get("srcset") or source_node.get("data-srcset")) if source_node else None
        if image_src:
            image_url = urljoin(BASE_URL, image_src.strip())

    # Product id is available in the review widget and/or favorite button attributes.
    product_id = None
    review_widget = card.select_one("[data-product-id]")
    if review_widget:
        product_id = review_widget.get("data-product-id")
    favorite_button = card.select_one("button.js-favorites[data-id]")
    if not product_id and favorite_button:
        product_id = favorite_button.get("data-id")

    sku = None  # SKU is not exposed in the supplied collection-card HTML.

    review_data = card.select_one(".wrap-inner[data-average-rating], .cus-star2 [data-average-rating]")
    rating = review_count = None
    if review_data:
        rating = parse_float(review_data.get("data-average-rating"))
        review_count = parse_int(review_data.get("data-number-of-reviews"))

    # This card's markup does not expose a separate rating percentage.
    rating_percent = None

    if not product_name:
        return None, "missing_product_name"
    if current_price is None or current_price <= 0:
        return None, "missing_or_invalid_current_price"

    return {
        "source": "thegioiskinfood",
        "category": CATEGORY,
        "product_id": str(product_id) if product_id else None,
        "sku": sku,
        "product_name": product_name,
        "brand": brand,
        "current_price_vnd": current_price,
        "current_price_max_vnd": current_price_max,
        "listed_price_vnd": listed_price,
        "listed_price_max_vnd": listed_price_max,
        "discount_percent": discount_percent,
        "rating": rating,
        "rating_percent": rating_percent,
        "review_count": review_count,
        "product_url": product_url,
        "image_url": image_url,
        "collected_at": collected_at,
        "source_file": source_file,
    }, None


def write_csv(path: Path, fields: list[str], rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(HTML_DIR.glob("thegioiskinfood_kem_chong_nang_page_*.html"))
    if not files:
        print(f"No HTML files found: {HTML_DIR / 'thegioiskinfood_kem_chong_nang_page_*.html'}")
        print("Run fetch_thegioiskinfood_sunscreens.py first, or check HTML_DIR.")
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
                rejected.append({
                    "source_file": file.name,
                    "card_index": index,
                    "reason": reason,
                    "product_url": normalize_product_url(
                        (card.select_one("a[href*='/products/']") or {}).get("href", "")
                    ) or "",
                    "card_text": get_text(card)[:1000],
                })
                continue

            key = record["product_url"]
            if key not in by_url:
                by_url[key] = record
            else:
                duplicate_cards += 1
                existing = by_url[key]
                # Preserve first record and fill any missing fields from a duplicate card.
                for field, value in record.items():
                    if field == "collected_at":
                        continue
                    if missing(existing.get(field)) and not missing(value):
                        existing[field] = value
                if len(record["product_name"]) > len(existing["product_name"]):
                    existing["product_name"] = record["product_name"]

    raw_rows = list(by_url.values())
    write_csv(OUT_CSV, FIELDS, raw_rows)
    write_csv(
        REJECTED_CSV,
        ["source_file", "card_index", "reason", "product_url", "card_text"],
        rejected,
    )

    df = pd.DataFrame(raw_rows, columns=FIELDS)
    if df.empty:
        qa_rows = []
        report_rows = [
            ("html_files", len(files)),
            ("candidate_cards", total_cards),
            ("unique_products", 0),
            ("duplicate_cards_skipped", duplicate_cards),
            ("rejected_cards", len(rejected)),
        ]
    else:
        df["qa_missing_product_id"] = df["product_id"].map(missing)
        df["qa_missing_product_name"] = df["product_name"].map(missing)
        df["qa_missing_brand"] = df["brand"].map(missing)
        df["qa_missing_product_url"] = df["product_url"].map(missing)

        current_price = pd.to_numeric(df["current_price_vnd"], errors="coerce")
        listed_price = pd.to_numeric(df["listed_price_vnd"], errors="coerce")
        discount = pd.to_numeric(df["discount_percent"], errors="coerce")
        rating = pd.to_numeric(df["rating"], errors="coerce")
        rating_percent = pd.to_numeric(df["rating_percent"], errors="coerce")
        review_count = pd.to_numeric(df["review_count"], errors="coerce")

        df["qa_missing_current_price"] = current_price.isna()
        df["qa_invalid_current_price"] = current_price.notna() & current_price.le(0)
        df["qa_missing_listed_price"] = listed_price.isna()
        df["qa_invalid_listed_price"] = listed_price.notna() & listed_price.le(0)
        df["qa_missing_discount_percent"] = discount.isna()
        df["qa_invalid_discount_percent"] = discount.notna() & ((discount < 0) | (discount > 100))
        df["qa_missing_rating"] = rating.isna()
        # Rating is sourced from data-average-rating, which appears to use a 5-star scale.
        df["qa_invalid_rating"] = rating.notna() & ((rating < 0) | (rating > 5))
        df["qa_missing_rating_percent"] = rating_percent.isna()
        df["qa_invalid_rating_percent"] = rating_percent.notna() & ((rating_percent < 0) | (rating_percent > 100))
        df["qa_missing_review_count"] = review_count.isna()
        df["qa_invalid_review_count"] = review_count.notna() & ((review_count < 0) | (review_count % 1 != 0))
        df["qa_missing_collected_at"] = df["collected_at"].map(missing)
        df["qa_price_above_listed_price"] = (
            current_price.notna() & listed_price.notna() & (current_price > listed_price)
        )
        normalized_urls = df["product_url"].map(
            lambda value: str(value).split("#", 1)[0].rstrip("/") if not missing(value) else None
        )
        duplicate_mask = normalized_urls.notna() & normalized_urls.duplicated(keep=False)
        df["qa_duplicate_product_url"] = duplicate_mask

        qa_rows = df[QA_FIELDS].to_dict("records")
        flag_columns = [column for column in QA_FIELDS if column.startswith("qa_")]
        report_rows = [
            ("html_files", len(files)),
            ("candidate_cards", total_cards),
            ("unique_products", len(raw_rows)),
            ("unique_product_urls", int(normalized_urls.nunique(dropna=True))),
            ("duplicate_cards_skipped", duplicate_cards),
            ("rejected_cards", len(rejected)),
        ]
        for column in flag_columns:
            report_rows.append((column.removeprefix("qa_"), int(df[column].fillna(False).astype(bool).sum())))

    write_csv(QA_CSV, QA_FIELDS, qa_rows)
    pd.DataFrame(report_rows, columns=["metric", "value"]).to_csv(
        QA_REPORT_CSV, index=False, encoding="utf-8-sig"
    )

    if not df.empty:
        flag_columns = [column for column in QA_FIELDS if column.startswith("qa_")]
        issues = df.loc[df[flag_columns].fillna(False).astype(bool).any(axis=1), QA_FIELDS].copy()
    else:
        issues = pd.DataFrame(columns=QA_FIELDS)
    issues.to_csv(QA_ISSUES_CSV, index=False, encoding="utf-8-sig")

    print("\nTHE GIOI SKINFOOD SUNSCREEN PARSER + QA SUMMARY")
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


