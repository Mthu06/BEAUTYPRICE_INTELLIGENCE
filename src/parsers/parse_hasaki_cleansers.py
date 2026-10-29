"""
Parse Hasaki cleanser category HTML and automatically create a QA-enriched dataset.

Outputs:
  data/interim/hasaki/hasaki_cleansers.csv
  data/interim/hasaki/hasaki_cleansers_qa.csv
  data/interim/hasaki/hasaki_cleansers_rejected_cards.csv
  data/interim/hasaki/hasaki_cleansers_qa_report.csv

Run from project root:
  python src/parsers/parse_hasaki_cleansers.py

The QA product_type is a heuristic label based on product_name. Review ambiguous
cases before using product_type for price comparisons.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
HTML_DIR = ROOT / "data" / "raw" / "hasaki" / "html"
OUT_DIR = ROOT / "data" / "interim" / "hasaki"
OUT_CSV = OUT_DIR / "hasaki_cleansers.csv"
QA_CSV = OUT_DIR / "hasaki_cleansers_qa.csv"
REJECTED_CSV = OUT_DIR / "hasaki_cleansers_rejected_cards.csv"
QA_REPORT_CSV = OUT_DIR / "hasaki_cleansers_qa_report.csv"

FIELDS = [
    "source", "category", "product_name", "brand",
    "current_price_vnd", "listed_price_vnd", "discount_percent",
    "rating", "review_count", "product_url", "collected_at", "source_file",
]


def text_of(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_money(text: str):
    if not text:
        return None
    cleaned = text.replace("\xa0", " ").replace("₫", "").replace("đ", "").strip()
    digits = re.sub(r"[^\d]", "", cleaned)
    return int(digits) if digits else None


def parse_float(text: str):
    match = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(match.group(0).replace(",", ".")) if match else None


def parse_int(text: str):
    match = re.search(r"\d[\d.,]*", text or "")
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(0))
    return int(digits) if digits else None


def card_candidates(soup: BeautifulSoup):
    cards = soup.select("div.rounded-xl.bg-card")
    if cards:
        return cards

    found = []
    for anchor in soup.select('a[href*="/san-pham/"]'):
        parent = anchor
        for _ in range(6):
            if parent is None:
                break
            classes = parent.get("class", [])
            if "bg-card" in classes and "rounded-xl" in classes:
                found.append(parent)
                break
            parent = parent.parent
    return found


def parse_card(card, source_file: str, collected_at: str):
    anchor = card.select_one('a[href*="/san-pham/"]')
    if not anchor:
        return None, "missing product anchor"

    url = (anchor.get("href") or "").strip()
    parsed = urlparse(url)
    if parsed.netloc and not parsed.netloc.lower().endswith("hasaki.vn"):
        return None, "unexpected product domain"
    if "/san-pham/" not in parsed.path:
        return None, "not a product URL"
    if not parsed.netloc:
        url = "https://hasaki.vn" + (url if url.startswith("/") else "/" + url)

    name = text_of(card.select_one("h2"))
    if not name:
        name = (anchor.get("aria-label") or "").replace("View ", "").replace(" details", "").strip()
    brand = text_of(card.select_one("strong"))

    price_row = None
    for node in card.select("div.flex.gap-2\\.5.items-center"):
        spans = node.find_all("span", recursive=False)
        if spans:
            price_row = spans
            break
    if price_row is None:
        price_spans = [
            span for span in card.select("span")
            if "₫" in text_of(span) or "đ" in text_of(span).lower()
        ]
        price_row = price_spans[:2]

    current_price = parse_money(text_of(price_row[0])) if price_row else None
    listed_price = parse_money(text_of(price_row[1])) if len(price_row) > 1 else None

    discount_text = ""
    for node in card.select("div"):
        txt = text_of(node)
        if re.fullmatch(r"-\s*\d+\s*%", txt):
            discount_text = txt
            break
    discount = parse_float(discount_text)

    rating = None
    review_count = None
    for node in card.select("div"):
        classes = node.get("class", [])
        if "text-white" in classes and "text-[11px]" in classes:
            candidate = text_of(node)
            if re.fullmatch(r"\d+(?:[.,]\d+)?", candidate):
                rating = parse_float(candidate)
                break
    for node in card.select("span"):
        txt = text_of(node)
        if re.fullmatch(r"\(\s*\d[\d.,]*\s*\)", txt):
            review_count = parse_int(txt)
            break

    if not name:
        return None, "missing product name"
    if current_price is None or current_price <= 0:
        return None, "missing/invalid current price"

    return {
        "source": "hasaki",
        "category": "sua_rua_mat",
        "product_name": name,
        "brand": brand or None,
        "current_price_vnd": current_price,
        "listed_price_vnd": listed_price,
        "discount_percent": discount,
        "rating": rating,
        "review_count": review_count,
        "product_url": url,
        "collected_at": collected_at,
        "source_file": source_file,
    }, None


def classify_product_type(name: str) -> tuple[str, str]:
    """Heuristic classification; labels should be QA-reviewed for ambiguous names."""
    text = (name or "").strip().lower()
    if not text:
        return "unknown", "missing product name"

    has_combo_marker = bool(re.search(
        r"\bcombo\b|\bbộ sản phẩm\b|\bbộ đôi\b|\bbộ ba\b|\bset\b|\b\d+\s*món\b",
        text, flags=re.I
    ))
    has_plus = "+" in text
    has_multiple_different_items = has_plus or bool(re.search(
        r"\b(?:serum|nước tẩy trang|nước cân bằng|kem dưỡng|sữa dưỡng|chống nắng)\b",
        text, flags=re.I
    ))

    # Examples: "Combo 2 Sữa Rửa Mặt ...", "Combo 3 Gel Rửa Mặt ..."
    same_product_multipack = bool(re.search(
        r"\bcombo\s*[2-9]\s+(?:sữa rửa mặt|gel rửa mặt|kem rửa mặt)\b",
        text, flags=re.I
    )) and not has_plus and not has_multiple_different_items

    if same_product_multipack:
        return "multi_pack", "combo count + cleanser type in product name"
    if has_combo_marker:
        return "bundle", "bundle/set marker in product name"
    if re.search(r"\b(?:bộ|combo|set)\b", text, flags=re.I):
        return "unknown", "ambiguous bundle wording"
    return "single", "no bundle marker detected in product name"


def write_csv(path: Path, fieldnames: list[str], rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_qa(raw_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    qa_rows = []
    for row in raw_rows:
        product_type, reason = classify_product_type(row.get("product_name") or "")
        qa_row = dict(row)
        qa_row["product_type"] = product_type
        qa_row["product_type_reason"] = reason
        qa_rows.append(qa_row)

    df = pd.DataFrame(qa_rows)
    report = []
    if df.empty:
        report.append({"metric": "rows", "value": 0})
        return qa_rows, report

    report.extend([
        {"metric": "rows", "value": len(df)},
        {"metric": "unique_product_urls", "value": int(df["product_url"].nunique(dropna=True))},
        {"metric": "duplicate_product_urls", "value": int(df["product_url"].duplicated().sum())},
        {"metric": "missing_product_name", "value": int(df["product_name"].isna().sum())},
        {"metric": "missing_brand", "value": int(df["brand"].isna().sum())},
        {"metric": "missing_current_price", "value": int(df["current_price_vnd"].isna().sum())},
        {"metric": "missing_listed_price", "value": int(df["listed_price_vnd"].isna().sum())},
        {"metric": "missing_rating", "value": int(df["rating"].isna().sum())},
        {"metric": "missing_review_count", "value": int(df["review_count"].isna().sum())},
    ])
    for label, count in df["product_type"].value_counts(dropna=False).items():
        report.append({"metric": f"product_type_{label}", "value": int(count)})
    return qa_rows, report


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(HTML_DIR.glob("cleanser_page_*.html"))
    if not files:
        print(f"No files found: {HTML_DIR / 'cleanser_page_*.html'}")
        return 1

    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    by_url = {}
    rejected = []
    total_cards = 0

    for file in files:
        html = file.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        cards = card_candidates(soup)
        total_cards += len(cards)
        print(f"{file.name}: found {len(cards)} candidate cards")

        for card in cards:
            record, reason = parse_card(card, file.name, collected_at)
            if reason:
                rejected.append({
                    "source_file": file.name,
                    "reason": reason,
                    "snippet": text_of(card)[:500],
                })
                continue
            key = record["product_url"].split("#", 1)[0].rstrip("/")
            by_url.setdefault(key, record)

    raw_rows = list(by_url.values())
    write_csv(OUT_CSV, FIELDS, raw_rows)
    write_csv(REJECTED_CSV, ["source_file", "reason", "snippet"], rejected)

    qa_rows, report = build_qa(raw_rows)
    qa_fields = FIELDS + ["product_type", "product_type_reason"]
    write_csv(QA_CSV, qa_fields, qa_rows)
    write_csv(QA_REPORT_CSV, ["metric", "value"], report)

    print("\nCLEANSER PARSER SUMMARY")
    print(f"HTML files found: {len(files)}")
    print(f"Candidate cards: {total_cards}")
    print(f"Unique product URLs: {len(by_url)}")
    print(f"Rejected cards: {len(rejected)}")
    print(f"Products CSV: {OUT_CSV}")
    print(f"QA CSV: {QA_CSV}")
    print(f"Rejected cards CSV: {REJECTED_CSV}")
    print(f"QA report CSV: {QA_REPORT_CSV}")

    if qa_rows:
        print("\nPRODUCT TYPE COUNTS")
        for label, count in pd.Series([r["product_type"] for r in qa_rows]).value_counts().items():
            print(f"{label}: {count}")
    if len(by_url) == 0:
        print("WARNING: zero products parsed. The saved HTML may not contain rendered product cards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
