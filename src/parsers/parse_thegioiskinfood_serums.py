"""Parse saved The Gioi SkinFood serum-search HTML into product and QA datasets.

Run from project root:
    python src/parsers/parse_thegioiskinfood_serums.py

Input:
    data/raw/thegioiskinfood/html/serum/thegioiskinfood_serum_search_serum_duong.html

Outputs:
    data/interim/thegioiskinfood/thegioiskinfood_serums.csv
    data/interim/thegioiskinfood/thegioiskinfood_serums_qa.csv
    data/interim/thegioiskinfood/thegioiskinfood_serums_rejected_cards.csv
    data/interim/thegioiskinfood/thegioiskinfood_serums_qa_report.csv
    data/interim/thegioiskinfood/thegioiskinfood_serums_qa_issues.csv

This parser reads saved HTML only. It does not visit product pages, collect review
text, or modify the catalog or price_snapshots.csv.
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
HTML_DIR = ROOT / "data" / "raw" / "thegioiskinfood" / "html" / "serum"
HTML_FILE = HTML_DIR / "thegioiskinfood_serum_search_serum_duong.html"
OUT_DIR = ROOT / "data" / "interim" / "thegioiskinfood"
OUT_CSV = OUT_DIR / "thegioiskinfood_serums.csv"
QA_CSV = OUT_DIR / "thegioiskinfood_serums_qa.csv"
REJECTED_CSV = OUT_DIR / "thegioiskinfood_serums_rejected_cards.csv"
QA_REPORT_CSV = OUT_DIR / "thegioiskinfood_serums_qa_report.csv"
QA_ISSUES_CSV = OUT_DIR / "thegioiskinfood_serums_qa_issues.csv"

BASE_URL = "https://thegioiskinfood.com"
CATEGORY = "serum"

FIELDS = [
    "source", "category", "product_id", "sku", "product_name", "brand",
    "current_price_vnd", "current_price_max_vnd", "listed_price_vnd", "listed_price_max_vnd",
    "discount_percent", "discount_badge_text", "rating", "rating_percent", "review_count", "product_url", "image_url",
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
    """Parse VND amounts, including strings like '175.000 đ – 363.000 đ'."""
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


def parse_float(value: str | None):
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return float(match.group(0).replace(",", ".")) if match else None


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
    # Search widget adds cards incrementally; use its actual card selector only.
    return soup.select("a.tgsfw-card[href*='/products/']")


def is_out_of_scope_serum(name: str) -> bool:
    """Exclude obvious body-care and sunscreen serum results from facial serum dataset."""
    text = name.casefold()
    exclusion_terms = (
        "dưỡng thể", "body care", "body serum", "serum chống nắng",
        "sun serum", "chống nắng", "spf", "pa++++", "pa+++",
    )
    return any(term in text for term in exclusion_terms)


def parse_card(card, source_file: str, collected_at: str):
    href = card.get("href")
    product_url = normalize_product_url(href)
    if not product_url:
        return None, "invalid_product_url_or_domain"

    name_node = card.select_one(".tgsfw-tt")
    product_name = (card.get("data-n") or get_text(name_node) or "").strip()
    product_name = re.sub(r"\s+", " ", product_name)
    if not product_name:
        return None, "missing_product_name"
    if is_out_of_scope_serum(product_name):
        return None, "not_facial_serum_search_result"

    brand = get_text(card.select_one(".tgsfw-brand")) or None

    price_node = card.select_one(".tgsfw-pr")

    # A .tgsfw-old element explicitly identifies the crossed-out/listed price.
    old_node = card.select_one(".tgsfw-old")
    old_text = get_text(old_node)
    old_values = parse_money_values(old_text)
    listed_price = old_values[0] if old_values else None
    listed_price_max = old_values[-1] if old_values else None

    # Remove the crossed-out amount before interpreting the current price/range.
    price_text = get_text(price_node)
    if old_text:
        price_text = price_text.replace(old_text, "", 1)
    displayed_prices = parse_money_values(price_text)

    # data-p is the widget's numeric price value; visible price text can contain a range.
    data_price = parse_money_values(card.get("data-p", ""))
    current_price = data_price[0] if data_price else (displayed_prices[0] if displayed_prices else None)
    current_price_max = displayed_prices[-1] if len(displayed_prices) > 1 else current_price

    # The discount badge can be '-48%' or 'Giảm đến 43%'. Preserve the displayed value.
    discount_node = card.select_one(".tgsfw-off")
    discount_badge_text = get_text(discount_node) or None
    # A badge such as "Giảm đến 43%" may describe the maximum discount across
    # variants, so it must not be stored as an exact product discount.
    # Compute an exact value only when an explicit crossed-out/listed price exists.
    discount_percent = None
    if listed_price and current_price and listed_price >= current_price > 0:
        discount_percent = round((listed_price - current_price) / listed_price * 100, 2)

    image_node = card.select_one("img.tgsfw-im")
    image_url = None
    if image_node:
        image_src = image_node.get("src") or image_node.get("data-src")
        if image_src:
            image_url = urljoin(BASE_URL, image_src.strip())

    # Search-card markup supplies a product slug but not a numeric product ID or SKU.
    # Do not fabricate identifiers or ratings that are not present in this HTML.
    # Use the stable product slug as a source-local identifier; do not invent a numeric ID.
    product_slug = urlparse(product_url).path.rstrip("/").split("/")[-1]
    product_id = product_slug or None
    sku = None
    rating = None
    rating_percent = None
    review_count = None

    if current_price is None or current_price <= 0:
        return None, "missing_or_invalid_current_price"

    return {
        "source": "thegioiskinfood",
        "category": CATEGORY,
        "product_id": product_id,
        "sku": sku,
        "product_name": product_name,
        "brand": brand,
        "current_price_vnd": current_price,
        "current_price_max_vnd": current_price_max,
        "listed_price_vnd": listed_price,
        "listed_price_max_vnd": listed_price_max,
        "discount_percent": discount_percent,
        "discount_badge_text": discount_badge_text,
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
    files = [HTML_FILE] if HTML_FILE.exists() else sorted(HTML_DIR.glob("*serum*duong*.html"))
    if not files:
        print(f"No serum-search HTML found: {HTML_FILE}")
        print("Run fetch_thegioiskinfood_serum.py first and check HTML_DIR.")
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
        print(f"{file.name}: found {len(cards)} candidate product cards")
        if not cards:
            print("  WARNING: no a.tgsfw-card product cards recognized in this HTML.")
        for index, card in enumerate(cards, start=1):
            record, reason = parse_card(card, file.name, collected_at)
            if reason:
                reason_counts[reason] += 1
                rejected.append({
                    "source_file": file.name,
                    "card_index": index,
                    "reason": reason,
                    "product_url": normalize_product_url(card.get("href")) or "",
                    "product_name": (card.get("data-n") or get_text(card.select_one(".tgsfw-tt")))[:500],
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
                    if field != "collected_at" and missing(existing.get(field)) and not missing(value):
                        existing[field] = value

    raw_rows = list(by_url.values())
    write_csv(OUT_CSV, FIELDS, raw_rows)
    write_csv(
        REJECTED_CSV,
        ["source_file", "card_index", "reason", "product_url", "product_name", "card_text"],
        rejected,
    )

    df = pd.DataFrame(raw_rows, columns=FIELDS)
    if df.empty:
        report_rows = [
            ("html_files", len(files)),
            ("candidate_cards", total_cards),
            ("unique_products", 0),
            ("duplicate_cards_skipped", duplicate_cards),
            ("rejected_cards", len(rejected)),
        ]
        qa_rows = []
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
        df["qa_duplicate_product_url"] = normalized_urls.notna() & normalized_urls.duplicated(keep=False)
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

    print("\nTHE GIOI SKINFOOD SERUM SEARCH PARSER + QA SUMMARY")
    print(f"HTML files found: {len(files)}")
    print(f"Candidate cards: {total_cards}")
    print(f"Unique facial-serum products: {len(raw_rows)}")
    print(f"Duplicate cards skipped: {duplicate_cards}")
    print(f"Rejected cards: {len(rejected)}")
    print(f"Rejection reasons: {dict(reason_counts)}")
    print(f"Products CSV: {OUT_CSV}")
    print(f"QA CSV: {QA_CSV}")
    print(f"Rejected cards CSV: {REJECTED_CSV}")
    print(f"QA report CSV: {QA_REPORT_CSV}")
    print(f"QA issues CSV: {QA_ISSUES_CSV}")
    print("Note: this script parses saved HTML only; it does not modify price_snapshots.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

