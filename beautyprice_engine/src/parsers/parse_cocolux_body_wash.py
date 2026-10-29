"""Parse Cocolux body-wash category HTML and create QA-enriched CSVs.

Run from project root:
    python src/parsers/parse_cocolux_body_wash.py

Input:
    data/raw/cocolux/html/body_wash/cocolux_body_wash_page_*.html

This script only parses saved category HTML. It does not visit product pages,
fetch new HTML, append price snapshots, or rebuild the catalog.
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
HTML_DIR = ROOT / "data" / "raw" / "cocolux" / "html" / "body_wash"
OUT_DIR = ROOT / "data" / "interim" / "cocolux"
OUT_CSV = OUT_DIR / "cocolux_body_wash.csv"
QA_CSV = OUT_DIR / "cocolux_body_wash_qa.csv"
REJECTED_CSV = OUT_DIR / "cocolux_body_wash_rejected_cards.csv"
QA_REPORT_CSV = OUT_DIR / "cocolux_body_wash_qa_report.csv"
QA_ISSUES_CSV = OUT_DIR / "cocolux_body_wash_qa_issues.csv"

BASE_URL = "https://cocolux.com"
CATEGORY = "body_wash"

FIELDS = [
    "source", "category", "product_name", "brand", "current_price_vnd",
    "listed_price_vnd", "discount_percent", "rating", "review_count",
    "product_url", "collected_at", "source_file",
]
QA_FIELDS = FIELDS + [
    "product_type", "product_type_reason",
    "qa_missing_product_name", "qa_missing_brand", "qa_missing_product_url",
    "qa_missing_current_price", "qa_invalid_current_price",
    "qa_missing_listed_price", "qa_invalid_listed_price",
    "qa_missing_discount_percent", "qa_invalid_discount_percent",
    "qa_missing_rating", "qa_invalid_rating", "qa_missing_review_count",
    "qa_invalid_review_count", "qa_missing_collected_at", "qa_duplicate_product_url",
    "qa_price_above_listed_price", "qa_discount_mismatch",
    "qa_rating_all_five_suspected_placeholder",
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
    digits = re.sub(r"\D", "", value.replace("\xa0", " "))
    return int(digits) if digits else None


def parse_float(value: str | None):
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return float(match.group(0).replace(",", ".")) if match else None


def normalize_url(href: str | None) -> str | None:
    if not href:
        return None
    parsed = urlparse(urljoin(BASE_URL, href.strip()))
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() not in {"cocolux.com", "www.cocolux.com"}:
        return None
    # Product-card URLs end with -i.<product ID>.
    if not re.search(r"-i\.[A-Za-z0-9]+/?$", parsed.path):
        return None
    return f"https://cocolux.com{parsed.path}".rstrip("/")


def card_candidates(soup: BeautifulSoup):
    # Scope selectors to product cards, excluding brand/filter/promotion links.
    return soup.select(".list-product-index .item.item-product")


def parse_card(card, source_file: str, collected_at: str):
    link = card.select_one("h3 a[href*='-i.']") or card.select_one("a.img[href*='-i.']")
    if link is None:
        return None, "missing_product_link"

    product_url = normalize_url(link.get("href", ""))
    if not product_url:
        return None, "invalid_product_url_or_domain"

    product_name = (
        get_text(card.select_one(".info h3 a"))
        or (link.get("title") or "").strip()
        or get_text(link)
    )
    brand_node = card.select_one(".info .trademark a")
    brand = (brand_node.get("title") or get_text(brand_node)).strip() if brand_node else ""

    current_price = parse_money(get_text(card.select_one(".price .now")))
    listed_price = parse_money(get_text(card.select_one(".price .old")))
    displayed_discount = parse_float(get_text(card.select_one(".discount")))

    # Accept only a plain numeric score inside the star block.
    # Sales volume ("Đã bán") is not a review count.
    rating = None
    star = card.select_one(".rating-sales-info .star")
    if star:
        rating_text = get_text(star)
        if re.fullmatch(r"\s*\d+(?:[.,]\d+)?\s*", rating_text):
            rating = parse_float(rating_text)
    review_count = None

    if not product_name:
        return None, "missing_product_name"
    if current_price is None or current_price <= 0:
        return None, "missing_or_invalid_current_price"

    return {
        "source": "cocolux",
        "category": CATEGORY,
        "product_name": product_name,
        "brand": brand or None,
        "current_price_vnd": current_price,
        "listed_price_vnd": listed_price,
        "discount_percent": displayed_discount,
        "rating": rating,
        "review_count": review_count,
        "product_url": product_url,
        "collected_at": collected_at,
        "source_file": source_file,
    }, None


def classify_product_type(name: Any) -> tuple[str, str]:
    text = "" if missing(name) else str(name).strip().lower()
    if not text:
        return "unknown", "missing product_name"
    if re.search(r"\bmua\s*\d+\s*tặng\s*\d+", text):
        return "bundle", "buy-X-get-Y promotion; verify actual pack composition"
    if re.search(
        r"\b(?:[2-9]\s*(?:chai|tuýp|lọ|hộp|miếng|gói)|(?:pack|lốc)\s*[2-9]|"
        r"[2-9]\s*[x×]\s*\d+\s*(?:ml|g))\b", text
    ):
        return "multi_pack", "explicit quantity/multipack marker; verify title and pack composition"
    if re.search(r"\b(combo|set|bộ sản phẩm|bộ đôi|bộ ba)\b", text):
        return "unknown", "ambiguous bundle/set wording; manual review recommended"
    return "single", "no explicit bundle or multipack marker detected"


def write_csv(path: Path, fields: list[str], rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(HTML_DIR.glob("cocolux_body_wash_page_*.html"))
    if not files:
        raise FileNotFoundError(
            f"Không tìm thấy cocolux_body_wash_page_*.html tại {HTML_DIR}"
        )

    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    by_url: dict[str, dict] = {}
    rejected: list[dict] = []
    reason_counts = Counter()
    total_cards = 0
    duplicate_cards = 0

    # Fetch snapshots are cumulative: later states contain earlier cards.
    # Deduplicate by normalized product URL, not by every anchor in the HTML.
    for file in files:
        html = file.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        cards = card_candidates(soup)
        total_cards += len(cards)
        print(f"{file.name}: found {len(cards)} candidate product cards")

        for index, card in enumerate(cards, start=1):
            record, reason = parse_card(card, file.name, collected_at)
            if reason:
                reason_counts[reason] += 1
                link = card.select_one("h3 a[href*='-i.']") or card.select_one("a.img[href*='-i.']")
                rejected.append({
                    "source_file": file.name,
                    "card_index": index,
                    "reason": reason,
                    "product_url": normalize_url(link.get("href", "")) if link else "",
                    "card_text": get_text(card)[:1000],
                })
                continue

            url = record["product_url"]
            if url in by_url:
                duplicate_cards += 1
                old = by_url[url]
                # Prefer the latest card, but retain non-empty values if omitted later.
                for field in FIELDS:
                    if field in {"collected_at", "source_file", "product_url", "source", "category"}:
                        continue
                    if old.get(field) in (None, "") and record.get(field) not in (None, ""):
                        old[field] = record[field]
            by_url[url] = record

    raw_rows = list(by_url.values())
    ratings = [row["rating"] for row in raw_rows if row["rating"] is not None]
    all_ratings_five = bool(ratings) and all(value == 5.0 for value in ratings)

    qa_rows = []
    for row in raw_rows:
        product_type, product_type_reason = classify_product_type(row["product_name"])
        current = row["current_price_vnd"]
        listed = row["listed_price_vnd"]
        displayed_discount = row["discount_percent"]
        calculated_discount = (
            round((listed - current) / listed * 100, 2)
            if listed is not None and listed > 0 and current is not None and current <= listed
            else None
        )
        qa = dict(row)
        qa.update({
            "product_type": product_type,
            "product_type_reason": product_type_reason,
            "qa_missing_product_name": missing(row["product_name"]),
            "qa_missing_brand": missing(row["brand"]),
            "qa_missing_product_url": missing(row["product_url"]),
            "qa_missing_current_price": current is None,
            "qa_invalid_current_price": current is not None and current <= 0,
            "qa_missing_listed_price": listed is None,
            "qa_invalid_listed_price": listed is not None and listed <= 0,
            "qa_missing_discount_percent": displayed_discount is None,
            "qa_invalid_discount_percent": displayed_discount is not None and not (0 <= displayed_discount <= 100),
            "qa_missing_rating": row["rating"] is None,
            "qa_invalid_rating": row["rating"] is not None and not (0 <= row["rating"] <= 5),
            "qa_missing_review_count": row["review_count"] is None,
            "qa_invalid_review_count": row["review_count"] is not None and row["review_count"] < 0,
            "qa_missing_collected_at": missing(row["collected_at"]),
            "qa_duplicate_product_url": False,
            "qa_price_above_listed_price": current is not None and listed is not None and current > listed,
            "qa_discount_mismatch": (
                displayed_discount is not None and calculated_discount is not None
                and abs(displayed_discount - calculated_discount) > 2
            ),
            # The HTML sample shows a visible score of 5, but a uniform 5.0
            # across all cards may be a template/default value; verify before use.
            "qa_rating_all_five_suspected_placeholder": all_ratings_five and row["rating"] == 5.0,
        })
        qa_rows.append(qa)

    write_csv(OUT_CSV, FIELDS, raw_rows)
    write_csv(QA_CSV, QA_FIELDS, qa_rows)
    write_csv(
        REJECTED_CSV,
        ["source_file", "card_index", "reason", "product_url", "card_text"],
        rejected,
    )

    report_rows = [
        ("html_files", len(files)),
        ("candidate_cards_across_snapshots", total_cards),
        ("unique_products", len(raw_rows)),
        ("duplicate_cards_skipped_or_overwritten", duplicate_cards),
        ("rejected_cards", len(rejected)),
        ("rating_all_five_suspected_placeholder", int(all_ratings_five)),
    ]
    for col in [c for c in QA_FIELDS if c.startswith("qa_")]:
        report_rows.append((col.removeprefix("qa_"), sum(bool(row[col]) for row in qa_rows)))
    for label, count in pd.Series([r["product_type"] for r in qa_rows]).value_counts(dropna=False).items():
        report_rows.append((f"product_type_{label}", int(count)))
    pd.DataFrame(report_rows, columns=["metric", "value"]).to_csv(
        QA_REPORT_CSV, index=False, encoding="utf-8-sig"
    )

    flag_columns = [c for c in QA_FIELDS if c.startswith("qa_")]
    issues = [row for row in qa_rows if any(bool(row[col]) for col in flag_columns)]
    write_csv(QA_ISSUES_CSV, QA_FIELDS, issues)

    print("\nCOCOLUX BODY WASH PARSER + QA SUMMARY")
    print(f"HTML files found: {len(files)}")
    print(f"Candidate cards across snapshots: {total_cards}")
    print(f"Unique products: {len(raw_rows)}")
    print(f"Duplicate cards skipped/overwritten: {duplicate_cards}")
    print(f"Rejected cards: {len(rejected)}")
    print(f"Rejection reasons: {dict(reason_counts)}")
    print(f"Products CSV: {OUT_CSV}")
    print(f"QA CSV: {QA_CSV}")
    print(f"Rejected cards CSV: {REJECTED_CSV}")
    print(f"QA report CSV: {QA_REPORT_CSV}")
    print(f"QA issues CSV: {QA_ISSUES_CSV}")
    print("Note: rating is parsed only when the star block contains a plain numeric score.")
    print("Note: if all parsed ratings are 5.0, QA flags them as a possible placeholder.")
    print("Note: 'Đã bán' is sales volume, not review_count; review_count remains missing.")
    print("Note: this script does not modify price_snapshots.csv or rebuild the catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

