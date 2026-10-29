"""Parse Hasaki body-exfoliator HTML and create product + QA datasets.

Run from project root:
    python src/parsers/parse_hasaki_exfoliators.py

Input:
    data/raw/hasaki/html/tay_te_bao_chet_body/tay_te_bao_chet_body_page_*.html

Outputs:
    data/interim/hasaki/hasaki_exfoliators.csv
    data/interim/hasaki/hasaki_exfoliators_qa.csv
    data/interim/hasaki/hasaki_exfoliators_rejected_cards.csv
    data/interim/hasaki/hasaki_exfoliators_qa_report.csv
    data/interim/hasaki/hasaki_exfoliators_qa_issues.csv

This parser follows the raw -> parsed -> QA pattern used by the supplied
Hasaki category parsers. It does not modify products.csv or price_snapshots.csv.
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
HTML_DIR = ROOT / "data" / "raw" / "hasaki" / "html" / "tay_te_bao_chet_body"
OUT_DIR = ROOT / "data" / "interim" / "hasaki"
OUT_CSV = OUT_DIR / "hasaki_exfoliators.csv"
QA_CSV = OUT_DIR / "hasaki_exfoliators_qa.csv"
REJECTED_CSV = OUT_DIR / "hasaki_exfoliators_rejected_cards.csv"
QA_REPORT_CSV = OUT_DIR / "hasaki_exfoliators_qa_report.csv"
QA_ISSUES_CSV = OUT_DIR / "hasaki_exfoliators_qa_issues.csv"

BASE_URL = "https://hasaki.vn"
CATEGORY = "Tẩy tế bào chết body"
CATEGORY_CODE = "tay_te_bao_chet_body"

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
    "qa_invalid_review_count", "qa_missing_collected_at",
    "qa_duplicate_product_url", "qa_price_above_listed_price",
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
    # Drop query/fragment to make duplicate matching stable.
    return f"https://hasaki.vn{parsed.path}".rstrip("/")


def card_candidates(soup: BeautifulSoup):
    # Matches the card class shown in the supplied Hasaki HTML snippet.
    cards = soup.select("div.rounded-xl.bg-card")
    if cards:
        return cards

    found = []
    seen = set()
    for anchor in soup.select('a[href*="/san-pham/"]'):
        parent = anchor
        for _ in range(8):
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

    # The supplied HTML uses span.text-orange.font-bold for current price
    # and span.line-through for listed/original price.
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

    if current_price is None:
        price_texts = [
            get_text(span) for span in card.select("span")
            if "₫" in get_text(span) or "đ" in get_text(span).lower()
        ]
        if price_texts:
            current_price = parse_money(price_texts[0])
            if listed_price is None and len(price_texts) > 1:
                listed_price = parse_money(price_texts[1])

    discount = None
    if (
        listed_price is not None and listed_price > 0
        and current_price is not None and current_price <= listed_price
    ):
        discount = round((listed_price - current_price) / listed_price * 100, 2)
    else:
        for node in card.select("div, span"):
            text = get_text(node)
            if re.fullmatch(r"-\s*\d+(?:[.,]\d+)?\s*%", text):
                discount = parse_float(text)
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
        text = get_text(span)
        if re.fullmatch(r"\(\s*\d[\d.,]*\s*\)", text):
            review_count = parse_int(text)
            break

    if not product_name:
        return None, "missing_product_name"
    if current_price is None or current_price <= 0:
        return None, "missing_or_invalid_current_price"

    return {
        "source": "hasaki",
        "category": CATEGORY_CODE,
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
    """Heuristic title-based type; review ambiguous bundles manually."""
    text = "" if missing(name) else str(name).strip().lower()
    if not text:
        return "unknown", "missing product_name"

    # Explicit purchase promotion does not prove pack composition.
    if re.search(r"mua\s*\d+\s*tặng\s*\d+", text):
        return "bundle", "buy-X-get-Y promotion; verify actual pack composition"

    # A bundle may contain a body scrub plus another product, as in the sample.
    mixed_bundle = re.search(
        r"\b(combo|set|bộ sản phẩm|bộ đôi|bộ ba)\b.*"
        r"(?:\+|sữa tắm|dưỡng thể|kem dưỡng|body lotion|shower gel)",
        text,
    )
    if mixed_bundle or "+" in text:
        return "bundle", "bundle marker or multiple product types in title"

    same_category_multipack = re.search(
        r"\bcombo\s*[2-9]\s+(?:tẩy tế bào chết|tẩy da chết|scrub)\b", text
    )
    generic_multipack = re.search(
        r"\b(?:[2-9]\s*(?:chai|tuýp|lọ|hộp|gói)|(?:pack|lốc)\s*[2-9]|"
        r"[2-9]\s*[x×]\s*\d+\s*(?:ml|g))\b",
        text,
    )
    if same_category_multipack or generic_multipack:
        return "multi_pack", "explicit quantity/multipack marker; verify pack composition"

    if re.search(r"\b(combo|set|bộ|tặng kèm|quà tặng)\b", text):
        return "unknown", "ambiguous bundle/gift wording; manual review recommended"

    return "single", "no explicit bundle or multipack marker detected"


def write_csv(path: Path, fields: list[str], rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(HTML_DIR.glob("tay_te_bao_chet_body_page_*.html"))
    if not files:
        raise FileNotFoundError(
            f"Không tìm thấy file tay_te_bao_chet_body_page_*.html tại {HTML_DIR}"
        )

    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    by_url: dict[str, dict] = {}
    rejected: list[dict] = []
    reason_counts = Counter()
    total_cards = 0

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
                link = card.select_one('a[href*="/san-pham/"]')
                rejected.append({
                    "source_file": file.name,
                    "card_index": index,
                    "reason": reason,
                    "product_url": normalize_url(link.get("href", "")) if link else "",
                    "card_text": get_text(card)[:1000],
                })
                continue

            url = record["product_url"]
            if url not in by_url:
                by_url[url] = record
            else:
                old = by_url[url]
                for field in FIELDS:
                    if field == "collected_at":
                        continue
                    if missing(old.get(field)) and not missing(record.get(field)):
                        old[field] = record[field]
                if len(record["product_name"]) > len(old["product_name"]):
                    old["product_name"] = record["product_name"]

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
            ("rejected_cards", len(rejected)),
        ]
    else:
        labels = df["product_name"].map(classify_product_type)
        df["product_type"] = labels.map(lambda value: value[0])
        df["product_type_reason"] = labels.map(lambda value: value[1])

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
        # Hasaki ratings may use a 10-point scale; don't assume a 5-point scale.
        df["qa_invalid_rating"] = rating.notna() & ((rating < 0) | (rating > 10))
        df["qa_missing_review_count"] = review_count.isna()
        df["qa_invalid_review_count"] = review_count.notna() & (
            (review_count < 0) | (review_count % 1 != 0)
        )
        df["qa_missing_collected_at"] = df["collected_at"].map(missing)
        df["qa_price_above_listed_price"] = (
            current_price.notna() & listed_price.notna() & (current_price > listed_price)
        )
        urls = df["product_url"].map(
            lambda value: str(value).split("#", 1)[0].rstrip("/") if not missing(value) else None
        )
        df["qa_duplicate_product_url"] = urls.notna() & urls.duplicated(keep=False)

        qa_rows = df[QA_FIELDS].to_dict("records")
        flag_columns = [column for column in QA_FIELDS if column.startswith("qa_")]
        report_rows = [
            ("html_files", len(files)),
            ("candidate_cards", total_cards),
            ("unique_products", len(raw_rows)),
            ("unique_product_urls", int(urls.nunique(dropna=True))),
            ("rejected_cards", len(rejected)),
        ]
        for column in flag_columns:
            report_rows.append((
                column.removeprefix("qa_"),
                int(df[column].fillna(False).astype(bool).sum()),
            ))
        for label, count in df["product_type"].value_counts(dropna=False).items():
            report_rows.append((f"product_type_{label}", int(count)))

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

    print("\nHASAKI BODY EXFOLIATOR PARSER + QA SUMMARY")
    print(f"HTML files found: {len(files)}")
    print(f"Candidate cards: {total_cards}")
    print(f"Unique products: {len(raw_rows)}")
    print(f"Rejected cards: {len(rejected)}")
    print(f"Rejection reasons: {dict(reason_counts)}")
    print(f"Products CSV: {OUT_CSV}")
    print(f"QA CSV: {QA_CSV}")
    print(f"Rejected cards CSV: {REJECTED_CSV}")
    print(f"QA report CSV: {QA_REPORT_CSV}")
    print(f"QA issues CSV: {QA_ISSUES_CSV}")
    if not df.empty:
        print("Product type counts:")
        print(df["product_type"].value_counts(dropna=False).to_string())
    print("Note: this parser does not modify products.csv or price_snapshots.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

