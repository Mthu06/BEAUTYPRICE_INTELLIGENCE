"""Parse Hasaki sunscreen HTML and automatically create QA-enriched datasets.

Run from project root:
    python src/parsers/parse_hasaki_sunscreens.py

Inputs:
    data/raw/hasaki/html/hasaki_page_*.html

Outputs:
    data/interim/hasaki/hasaki_sunscreens.csv
    data/interim/hasaki/hasaki_sunscreens_qa.csv
    data/interim/hasaki/hasaki_sunscreens_rejected_cards.csv
    data/interim/hasaki/hasaki_sunscreens_qa_report.csv

This follows the same raw -> QA -> normalized pipeline as parse_hasaki_cleansers.py.
Product type is a rule-based estimate from the title and ambiguous cases should be reviewed.
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
HTML_DIR = ROOT / "data" / "raw" / "hasaki" / "html"
OUT_DIR = ROOT / "data" / "interim" / "hasaki"
OUT_CSV = OUT_DIR / "hasaki_sunscreens.csv"
QA_CSV = OUT_DIR / "hasaki_sunscreens_qa.csv"
REJECTED_CSV = OUT_DIR / "hasaki_sunscreens_rejected_cards.csv"
QA_REPORT_CSV = OUT_DIR / "hasaki_sunscreens_qa_report.csv"
BASE_URL = "https://hasaki.vn"
CATEGORY = "Kem chống nắng"

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
    "qa_price_above_listed_price",
]


def get_text(element) -> str:
    return element.get_text(" ", strip=True) if element else ""


def missing(value: Any) -> bool:
    try:
        return value is None or bool(pd.isna(value)) or str(value).strip() == ""
    except (TypeError, ValueError):
        return value is None


def parse_money(value: str):
    if not value:
        return None
    digits = re.sub(r"\D", "", value.replace("\xa0", " "))
    return int(digits) if digits else None


def parse_float(value: str):
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return float(match.group(0).replace(",", ".")) if match else None


def parse_int(value: str):
    match = re.search(r"\d[\d.,]*", value or "")
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    return int(digits) if digits else None


def normalize_url(href: str | None) -> str | None:
    if not href:
        return None
    parsed = urlparse(urljoin(BASE_URL, href.strip()))
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() not in {"hasaki.vn", "www.hasaki.vn"}:
        return None
    if not parsed.path.startswith("/san-pham/"):
        return None
    return f"https://hasaki.vn{parsed.path}".rstrip("/")


def card_candidates(soup: BeautifulSoup):
    cards = soup.select("div.rounded-xl.bg-card")
    if cards:
        return cards
    found = []
    seen = set()
    for anchor in soup.select('a[href*="/san-pham/"]'):
        parent = anchor
        for _ in range(6):
            if parent is None:
                break
            classes = parent.get("class", [])
            if "bg-card" in classes and "rounded-xl" in classes:
                if id(parent) not in seen:
                    found.append(parent)
                    seen.add(id(parent))
                break
            parent = parent.parent
    return found


def parse_card(card, source_file: str, collected_at: str):
    link = card.select_one('a[href*="/san-pham/"]')
    if link is None:
        return None, "missing_product_link"
    product_url = normalize_url(link.get("href", ""))
    if not product_url:
        return None, "invalid_product_url_or_domain"

    product_name = ""
    for selector in ("h2", "h3", '[itemprop="name"]'):
        product_name = get_text(card.select_one(selector))
        if product_name:
            break
    if not product_name:
        product_name = (link.get("aria-label") or link.get("title") or "").strip()
        product_name = re.sub(r"^\s*View\s+|\s+details\s*$", "", product_name, flags=re.I)
    brand = get_text(card.select_one("strong"))

    current_price_text = (
        get_text(card.select_one("span.text-orange.font-bold"))
        or get_text(card.select_one('[class*="text-orange"][class*="font-bold"]'))
    )
    listed_price_text = (
        get_text(card.select_one("span.line-through"))
        or get_text(card.select_one('[class*="line-through"]'))
    )
    current_price = parse_money(current_price_text)
    listed_price = parse_money(listed_price_text)

    # Fallback for HTML variants where price classes differ.
    if current_price is None:
        price_texts = [get_text(s) for s in card.select("span") if ("₫" in get_text(s) or "đ" in get_text(s).lower())]
        if price_texts:
            current_price = parse_money(price_texts[0])
            if listed_price is None and len(price_texts) > 1:
                listed_price = parse_money(price_texts[1])

    discount = None
    if listed_price and listed_price > 0 and current_price is not None and current_price <= listed_price:
        discount = round((listed_price - current_price) / listed_price * 100, 2)
    else:
        for node in card.select("div, span"):
            txt = get_text(node)
            if re.fullmatch(r"-\s*\d+(?:[.,]\d+)?\s*%", txt):
                discount = parse_float(txt)
                break

    rating = None
    rating_candidates = [
        get_text(card.select_one("div.bg-orange div.text-white")),
        get_text(card.select_one('[class*="text-white"][class*="text-[11px]"]')),
    ]
    for candidate in rating_candidates:
        if re.fullmatch(r"\d+(?:[.,]\d+)?", candidate or ""):
            rating = parse_float(candidate)
            break
    review_count = None
    for span in card.select("span"):
        txt = get_text(span)
        if re.fullmatch(r"\(\s*\d[\d.,]*\s*\)", txt):
            review_count = parse_int(txt)
            break

    if not product_name:
        return None, "missing_product_name"
    if current_price is None or current_price <= 0:
        return None, "missing_or_invalid_current_price"

    return {
        "source": "hasaki",
        "category": "kem_chong_nang",
        "product_name": product_name,
        "brand": brand or None,
        "current_price_vnd": current_price,
        "listed_price_vnd": listed_price,
        "discount_percent": discount,
        "rating": rating,
        "review_count": review_count,
        "product_url": product_url,
        "collected_at": collected_at,
        "source_file": source_file,
    }, None


def classify_product_type(name: Any) -> tuple[str, str]:
    """Classify product type from title only; ambiguous marketing titles stay unknown."""
    text = "" if missing(name) else str(name).strip().lower()
    if not text:
        return "unknown", "missing product_name"

    # A promotion is not necessarily the same thing as a physical multipack.
    if re.search(r"mua\s*\d+\s*tặng\s*\d+", text):
        return "bundle", "buy-X-get-Y promotion; verify actual pack composition"

    # Explicit same-category count, e.g. "Combo 2 Kem Chống Nắng ...".
    # This is a heuristic: the title alone cannot prove both units are identical.
    same_product_count = re.search(
        r"\bcombo\s*[2-9]\s+(?:kem|gel|sữa|tinh chất|xịt)?\s*chống nắng\b", text
    )
    generic_multipack = re.search(
        r"\b(?:[2-9]\s*(?:chai|tuýp|lọ|hộp|miếng|gói)|(?:pack|lốc)\s*[2-9]|[2-9]\s*[x×]\s*\d+\s*(?:ml|g))\b",
        text,
    )
    if same_product_count or generic_multipack:
        return "multi_pack", "explicit quantity/multipack marker; verify title and pack composition"

    # Explicit mixed sets or a bundle with different product types.
    mixed_bundle = re.search(
        r"\b(combo|set|bộ sản phẩm|bộ đôi|bộ ba)\b.*(?:\+|serum|nước tẩy trang|sữa rửa mặt|kem dưỡng|toner|nước cân bằng)",
        text,
    )
    if mixed_bundle:
        return "bundle", "bundle marker with multiple/different product types"

    if re.search(r"\b(combo|set|bộ|tặng kèm|quà tặng)\b", text):
        return "unknown", "ambiguous bundle/gift wording; manual review recommended"
    return "single", "no explicit bundle or multipack marker detected"


def write_csv(path: Path, fields: list[str], rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(HTML_DIR.glob("hasaki_page_*.html"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy HTML hasaki_page_*.html tại {HTML_DIR}")

    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    by_url: dict[str, dict] = {}
    rejected: list[dict] = []
    total_cards = 0
    reason_counts = Counter()

    for file in files:
        html = file.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        cards = card_candidates(soup)
        total_cards += len(cards)
        print(f"{file.name}: found {len(cards)} candidate cards")
        for index, card in enumerate(cards, start=1):
            record, reason = parse_card(card, file.name, collected_at)
            if reason:
                reason_counts[reason] += 1
                rejected.append({
                    "source_file": file.name,
                    "card_index": index,
                    "reason": reason,
                    "product_url": normalize_url((card.select_one('a[href*="/san-pham/"]') or {}).get("href", "")) or "",
                    "card_text": get_text(card)[:1000],
                })
                continue
            url = record["product_url"]
            if url not in by_url:
                by_url[url] = record
            else:
                old = by_url[url]
                # Keep first observation timestamp, fill missing attributes from duplicate cards.
                for field in FIELDS:
                    if field == "collected_at":
                        continue
                    if missing(old.get(field)) and not missing(record.get(field)):
                        old[field] = record[field]
                if len(record["product_name"]) > len(old["product_name"]):
                    old["product_name"] = record["product_name"]

    raw_rows = list(by_url.values())
    write_csv(OUT_CSV, FIELDS, raw_rows)
    write_csv(REJECTED_CSV, ["source_file", "card_index", "reason", "product_url", "card_text"], rejected)

    df = pd.DataFrame(raw_rows, columns=FIELDS)
    if df.empty:
        qa_rows = []
        report_rows = [("rows", 0), ("candidate_cards", total_cards), ("rejected_cards", len(rejected))]
    else:
        labels = df["product_name"].map(classify_product_type)
        df["product_type"] = labels.map(lambda x: x[0])
        df["product_type_reason"] = labels.map(lambda x: x[1])

        # Data-quality flags. Missing values stay missing; they are never replaced with zero.
        df["qa_missing_product_name"] = df["product_name"].map(missing)
        df["qa_missing_brand"] = df["brand"].map(missing)
        df["qa_missing_product_url"] = df["product_url"].map(missing)
        current_price = pd.to_numeric(df["current_price_vnd"], errors="coerce")
        listed_price = pd.to_numeric(df["listed_price_vnd"], errors="coerce")
        discount = pd.to_numeric(df["discount_percent"], errors="coerce")
        rating = pd.to_numeric(df["rating"], errors="coerce")
        review_count = pd.to_numeric(df["review_count"], errors="coerce")
        df["qa_missing_current_price"] = current_price.isna()
        df["qa_invalid_current_price"] = current_price.notna() & current_price.le(0)
        df["qa_missing_listed_price"] = listed_price.isna()
        df["qa_invalid_listed_price"] = listed_price.notna() & listed_price.le(0)
        df["qa_missing_discount_percent"] = discount.isna()
        df["qa_invalid_discount_percent"] = discount.notna() & ((discount < 0) | (discount > 100))
        df["qa_missing_rating"] = rating.isna()
        # Hasaki rating displays can use a 10-point scale; do not assume a 5-point scale.
        df["qa_invalid_rating"] = rating.notna() & ((rating < 0) | (rating > 10))
        df["qa_missing_review_count"] = review_count.isna()
        df["qa_invalid_review_count"] = review_count.notna() & ((review_count < 0) | (review_count % 1 != 0))
        df["qa_missing_collected_at"] = df["collected_at"].map(missing)
        df["qa_price_above_listed_price"] = (
            current_price.notna() & listed_price.notna() & (current_price > listed_price)
        )
        urls = df["product_url"].map(lambda x: str(x).split("#", 1)[0].rstrip("/") if not missing(x) else None)
        dup_mask = urls.notna() & urls.duplicated(keep=False)
        df["qa_duplicate_product_url"] = dup_mask
        qa_rows = df[QA_FIELDS].to_dict("records")
        flag_columns = [c for c in QA_FIELDS if c.startswith("qa_")]
        report_rows = [
            ("html_files", len(files)),
            ("candidate_cards", total_cards),
            ("unique_products", len(raw_rows)),
            ("unique_product_urls", int(urls.nunique(dropna=True))),
            ("rejected_cards", len(rejected)),
        ]
        for col in flag_columns:
            report_rows.append((col.removeprefix("qa_"), int(df[col].fillna(False).astype(bool).sum())))
        for label, count in df["product_type"].value_counts(dropna=False).items():
            report_rows.append((f"product_type_{label}", int(count)))

    write_csv(QA_CSV, QA_FIELDS, qa_rows)
    pd.DataFrame(report_rows, columns=["metric", "value"]).to_csv(QA_REPORT_CSV, index=False, encoding="utf-8-sig")

    # One row per product with at least one QA flag, to make manual review practical.
    if not df.empty:
        flag_columns = [c for c in QA_FIELDS if c.startswith("qa_")]
        issues = df.loc[df[flag_columns].fillna(False).astype(bool).any(axis=1), QA_FIELDS].copy()
    else:
        issues = pd.DataFrame(columns=QA_FIELDS)
    issues.to_csv(OUT_DIR / "hasaki_sunscreens_qa_issues.csv", index=False, encoding="utf-8-sig")

    print("\nHASAKI SUNSCREEN PARSER + QA SUMMARY")
    print(f"HTML files found: {len(files)}")
    print(f"Candidate cards: {total_cards}")
    print(f"Unique products: {len(raw_rows)}")
    print(f"Rejected cards: {len(rejected)}")
    print(f"Rejection reasons: {dict(reason_counts)}")
    print(f"Products CSV: {OUT_CSV}")
    print(f"QA CSV: {QA_CSV}")
    print(f"Rejected cards CSV: {REJECTED_CSV}")
    print(f"QA report CSV: {QA_REPORT_CSV}")
    print(f"QA issues CSV: {OUT_DIR / 'hasaki_sunscreens_qa_issues.csv'}")
    if not df.empty:
        print("Product type counts:")
        print(df["product_type"].value_counts(dropna=False).to_string())
    print("Note: this script parses HTML and does not modify price_snapshots.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

