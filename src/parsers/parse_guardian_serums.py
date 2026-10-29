"""Parse Guardian serum category HTML and create product + QA datasets.

Run from project root:
    python src/parsers/parse_guardian_serums.py

Input:
    data/raw/guardian/html/serum_tinh_chat/guardian_serum_tinh_chat_page_*.html

Outputs are written under data/interim/guardian/. This parser only reads saved HTML;
 it does not visit product pages or collect review text.
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
HTML_DIR = ROOT / "data" / "raw" / "guardian" / "html" / "serum_tinh_chat"
OUT_DIR = ROOT / "data" / "interim" / "guardian"
OUT_CSV = OUT_DIR / "guardian_serums.csv"
QA_CSV = OUT_DIR / "guardian_serums_qa.csv"
REJECTED_CSV = OUT_DIR / "guardian_serums_rejected_cards.csv"
QA_REPORT_CSV = OUT_DIR / "guardian_serums_qa_report.csv"
QA_ISSUES_CSV = OUT_DIR / "guardian_serums_qa_issues.csv"
BASE_URL = "https://www.guardian.com.vn"
CATEGORY = "serum_tinh_chat"

FIELDS = [
    "source", "category", "product_id", "sku", "product_name", "brand",
    "current_price_vnd", "listed_price_vnd", "discount_percent", "rating",
    "rating_percent", "review_count", "product_url", "image_url", "collected_at", "source_file",
]
QA_FIELDS = FIELDS + [
    "qa_missing_product_id", "qa_missing_product_name", "qa_missing_brand",
    "qa_missing_product_url", "qa_missing_current_price", "qa_invalid_current_price",
    "qa_missing_listed_price", "qa_invalid_listed_price", "qa_missing_discount_percent",
    "qa_invalid_discount_percent", "qa_missing_rating", "qa_invalid_rating",
    "qa_missing_rating_percent", "qa_invalid_rating_percent", "qa_missing_review_count",
    "qa_invalid_review_count", "qa_missing_collected_at", "qa_duplicate_product_url",
    "qa_price_above_listed_price",
]


def get_text(element) -> str:
    return element.get_text(" ", strip=True) if element else ""


def missing(value: Any) -> bool:
    try:
        return value is None or bool(pd.isna(value)) or str(value).strip() == ""
    except (TypeError, ValueError):
        return value is None


def parse_money(value: str | None):
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value).replace("\xa0", " "))
    return int(digits) if digits else None


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
    if parsed.netloc.lower() not in {"guardian.com.vn", "www.guardian.com.vn"}:
        return None
    if not parsed.path.lower().endswith(".html"):
        return None
    return f"{BASE_URL}{parsed.path}".rstrip("/")


def card_candidates(soup: BeautifulSoup):
    cards = soup.select("li.item.product.product-item")
    return cards if cards else soup.select("div.product-item-info[data-container='product-grid']")


def price_from_node(node):
    if not node:
        return None
    amount = node.select_one("[data-price-amount]")
    if amount and amount.get("data-price-amount"):
        return parse_money(amount.get("data-price-amount"))
    return parse_money(get_text(node))


def parse_card(card, source_file: str, collected_at: str):
    info = card.select_one("div.product-item-info") or card
    name_link = info.select_one("a.product-item-link")
    photo_link = info.select_one("a.product-item-photo")
    href = (name_link.get("href") if name_link else None) or (photo_link.get("href") if photo_link else None)
    product_url = normalize_product_url(href)
    if not product_url:
        return None, "missing_or_invalid_product_url"

    product_name = get_text(name_link)
    if not product_name and photo_link:
        image = photo_link.select_one("img.product-image-photo")
        product_name = (image.get("alt") or "").strip() if image else ""
    brand = get_text(info.select_one("a.product-item-brand-link")) or None

    product_id = None
    id_match = re.search(r"product-item-info_(\d+)", info.get("id", ""))
    if id_match:
        product_id = id_match.group(1)
    if not product_id:
        price_box_id = info.select_one(".price-box[data-product-id]")
        if price_box_id:
            product_id = price_box_id.get("data-product-id")
    form = info.select_one('form[data-role="tocart-form"]')
    sku = form.get("data-product-sku") if form else None

    image_node = info.select_one("img.product-image-photo")
    image_url = None
    if image_node:
        image_url = image_node.get("src") or image_node.get("data-src")
        if image_url:
            image_url = urljoin(BASE_URL, image_url.strip())

    price_box = info.select_one(".price-box")
    current_price = listed_price = None
    if price_box:
        special = price_box.select_one(".special-price")
        old = price_box.select_one(".old-price")
        if special:
            current_price = price_from_node(special)
            listed_price = price_from_node(old) if old else None
        else:
            current_price = price_from_node(price_box.select_one('[data-price-type="finalPrice"]'))
            if current_price is None:
                current_price = price_from_node(price_box)

    discount_node = price_box.select_one(".percent-discount") if price_box else None
    discount_percent = parse_float(get_text(discount_node)) if discount_node else None
    if discount_percent is None and current_price is not None and listed_price and listed_price >= current_price > 0:
        discount_percent = round((listed_price - current_price) / listed_price * 100, 2)

    summary = info.select_one(".product-reviews-summary")
    stars = summary.select_one(".reviews-actions .stars") if summary else None
    count = summary.select_one(".reviews-actions .count") if summary else None
    rating = parse_float(get_text(stars)) if stars else None
    review_count = parse_int(get_text(count)) if count else None
    rating_result = summary.select_one(".rating-result") if summary else None
    rating_percent = parse_float(rating_result.get("title", "")) if rating_result else None

    if not product_name:
        return None, "missing_product_name"
    if current_price is None or current_price <= 0:
        return None, "missing_or_invalid_current_price"

    return {
        "source": "guardian", "category": CATEGORY,
        "product_id": str(product_id) if product_id else None,
        "sku": str(sku).strip() if sku else None,
        "product_name": product_name, "brand": brand,
        "current_price_vnd": current_price, "listed_price_vnd": listed_price,
        "discount_percent": discount_percent, "rating": rating,
        "rating_percent": rating_percent, "review_count": review_count,
        "product_url": product_url, "image_url": image_url,
        "collected_at": collected_at, "source_file": source_file,
    }, None


def write_csv(path: Path, fields: list[str], rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(HTML_DIR.glob("guardian_serum_tinh_chat_page_*.html"))
    if not files:
        print(f"No HTML files found: {HTML_DIR / 'guardian_serum_tinh_chat_page_*.html'}")
        print("Run fetch_guardian_serums.py first, or check HTML_DIR.")
        return 1

    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    by_url: dict[str, dict] = {}
    rejected, reason_counts = [], Counter()
    total_cards = duplicate_cards = 0

    for file in files:
        soup = BeautifulSoup(file.read_text(encoding="utf-8", errors="replace"), "html.parser")
        cards = card_candidates(soup)
        total_cards += len(cards)
        print(f"{file.name}: found {len(cards)} candidate cards")
        for index, card in enumerate(cards, start=1):
            record, reason = parse_card(card, file.name, collected_at)
            if reason:
                reason_counts[reason] += 1
                rejected.append({"source_file": file.name, "card_index": index, "reason": reason,
                                 "product_url": "", "card_text": get_text(card)[:600]})
                continue
            key = record["product_url"]
            if key in by_url:
                duplicate_cards += 1
                existing = by_url[key]
                for field, value in record.items():
                    if missing(existing.get(field)) and not missing(value):
                        existing[field] = value
                continue
            by_url[key] = record

    rows = list(by_url.values())
    write_csv(OUT_CSV, FIELDS, rows)
    write_csv(REJECTED_CSV, ["source_file", "card_index", "reason", "product_url", "card_text"], rejected)
    df = pd.DataFrame(rows, columns=FIELDS)
    report = [("html_files", len(files)), ("candidate_cards", total_cards),
              ("parsed_unique_products", len(rows)), ("duplicate_cards_skipped", duplicate_cards),
              ("rejected_cards", len(rejected))]

    if not df.empty:
        df["qa_missing_product_id"] = df["product_id"].map(missing)
        df["qa_missing_product_name"] = df["product_name"].map(missing)
        df["qa_missing_brand"] = df["brand"].map(missing)
        df["qa_missing_product_url"] = df["product_url"].map(missing)
        current = pd.to_numeric(df["current_price_vnd"], errors="coerce")
        listed = pd.to_numeric(df["listed_price_vnd"], errors="coerce")
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
        df["qa_duplicate_product_url"] = df["product_url"].duplicated(keep=False)
        df["qa_price_above_listed_price"] = current.notna() & listed.notna() & (current > listed)
        qa_rows = df[QA_FIELDS].to_dict("records")
        for column in [col for col in QA_FIELDS if col.startswith("qa_")]:
            report.append((column.removeprefix("qa_"), int(df[column].fillna(False).astype(bool).sum())))
        report.append(("unique_product_urls", int(df["product_url"].nunique(dropna=True))))
    else:
        qa_rows = []

    write_csv(QA_CSV, QA_FIELDS, qa_rows)
    pd.DataFrame(report, columns=["metric", "value"]).to_csv(QA_REPORT_CSV, index=False, encoding="utf-8-sig")
    if not df.empty:
        flag_cols = [col for col in QA_FIELDS if col.startswith("qa_")]
        issues = df.loc[df[flag_cols].fillna(False).astype(bool).any(axis=1), QA_FIELDS].copy()
    else:
        issues = pd.DataFrame(columns=QA_FIELDS)
    issues.to_csv(QA_ISSUES_CSV, index=False, encoding="utf-8-sig")

    print("\nGUARDIAN SERUM PARSER + QA SUMMARY")
    print(f"HTML files found: {len(files)}")
    print(f"Candidate cards: {total_cards}")
    print(f"Unique products parsed: {len(rows)}")
    print(f"Duplicate cards skipped: {duplicate_cards}")
    print(f"Rejected cards: {len(rejected)}")
    print(f"Rejection reasons: {dict(reason_counts)}")
    print(f"Products CSV: {OUT_CSV}\nQA CSV: {QA_CSV}\nRejected cards CSV: {REJECTED_CSV}")
    print(f"QA report CSV: {QA_REPORT_CSV}\nQA issues CSV: {QA_ISSUES_CSV}")
    print("Listing ratings/counts are summaries only; review text is not collected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

