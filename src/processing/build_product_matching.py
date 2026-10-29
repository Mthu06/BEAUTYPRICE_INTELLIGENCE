"""
Audit and rebuild product_matching.csv from the normalized products catalog.

Run from project root:
    python src/processing/build_product_matching.py

Optional:
    python src/processing/build_product_matching.py --min-confidence 0.80

This version:
- Reads products.csv as the source of truth for product rows and retailer IDs.
- Normalizes retailer names/IDs so "The Gioi Skin Food" and "thegioiskinfood"
  are recognized as the same retailer.
- Creates cross-retailer *candidate groups* from conservative normalized names.
- Does not automatically confirm any match. All rows are pending and require review.
- Writes a separate review report for likely name matches with potentially different
  package sizes/variants.
- Does not modify products.csv, snapshots, or other pipeline outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PRODUCTS_FILE = PROCESSED_DIR / "products.csv"
DEFAULT_OUTPUT = PROCESSED_DIR / "product_matching.csv"
DEFAULT_REVIEW = PROCESSED_DIR / "product_matching_review.csv"

RETAILER_ALIASES = {
    "hasaki": "hasaki",
    "guardian": "guardian",
    "cocolux": "cocolux",
    "watsons": "watsons",
    "thegioiskinfood": "the_gioi_skin_food",
    "the_gioi_skin_food": "the_gioi_skin_food",
    "the_gioi_skinfood": "the_gioi_skin_food",
}

OUTPUT_COLUMNS = [
    "match_id",
    "match_group_id",
    "product_id",
    "retailer_id",
    "source_product_id",
    "source_product_name",
    "match_method",
    "match_confidence",
    "verified_by_human",
    "match_status",
]

REVIEW_COLUMNS = [
    "candidate_group_id",
    "product_id",
    "retailer_id",
    "product_name",
    "product_url",
    "normalized_name",
    "candidate_group_size",
    "candidate_retailer_count",
    "review_reason",
]


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).casefold().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_retailer(value: Any) -> str:
    key = normalize_text(value).replace(" ", "_")
    compact = key.replace("_", "")
    return RETAILER_ALIASES.get(key, RETAILER_ALIASES.get(compact, key))


def canonical_url(value: Any) -> str:
    if pd.isna(value):
        return ""
    url = str(value).strip().split("#", 1)[0]
    url = url.split("?", 1)[0].rstrip("/")
    return url.casefold()


def stable_id(*parts: Any, prefix: str) -> str:
    raw = "|".join("" if pd.isna(p) else str(p).strip() for p in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def extract_size_tokens(name: str) -> set[str]:
    """Extract explicit quantity tokens to avoid grouping different package sizes."""
    return set(re.findall(r"(?<![a-z0-9])\d+(?:[.,]\d+)?\s?(?:ml|g|kg|l|oz|pcs|pc|viên|vien)(?![a-z])", name))


def strip_size_tokens(name: str) -> str:
    return re.sub(
        r"(?<![a-z0-9])\d+(?:[.,]\d+)?\s?(?:ml|g|kg|l|oz|pcs|pc|vien)(?![a-z])",
        " ",
        name,
    ).strip()


def load_products() -> pd.DataFrame:
    if not PRODUCTS_FILE.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {PRODUCTS_FILE}. Hãy chạy build_beautyprice_datasets.py trước."
        )

    df = pd.read_csv(PRODUCTS_FILE, encoding="utf-8-sig", low_memory=False)
    required = {"product_id", "retailer_id", "product_name", "product_url"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"products.csv thiếu các cột bắt buộc: {sorted(missing)}")

    df = df.copy()
    df["product_id"] = df["product_id"].fillna("").astype(str).str.strip()
    df["retailer_id"] = df["retailer_id"].map(normalize_retailer)
    df["product_name"] = df["product_name"].fillna("").astype(str).str.strip()
    df["product_url"] = df["product_url"].fillna("").astype(str).str.strip()
    df["url_key"] = df["product_url"].map(canonical_url)
    df["normalized_name"] = df["product_name"].map(normalize_text)
    df["size_tokens"] = df["normalized_name"].map(extract_size_tokens)
    df["name_without_size"] = df["normalized_name"].map(strip_size_tokens)
    df = df[
        df["product_id"].ne("")
        & df["retailer_id"].ne("")
        & df["product_name"].ne("")
        & df["url_key"].ne("")
    ].copy()
    # One row per retailer + URL, as in the project catalog identity model.
    df = df.drop_duplicates(subset=["retailer_id", "url_key"], keep="first")
    return df.reset_index(drop=True)


def build_candidate_groups(df: pd.DataFrame, min_confidence: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Group only exact normalized names across retailers automatically as candidates.
    Similar names with differing explicit sizes are placed in a review report, not
    automatically grouped.
    """
    df = df.copy()
    df["candidate_group_id"] = ""
    df["match_method"] = ""
    df["match_confidence"] = 0.0
    df["review_reason"] = ""

    # Exact normalized names are safer than fuzzy matching; still pending until verified.
    exact_group_ids: dict[str, str] = {}
    for name, group in df.groupby("normalized_name", sort=False):
        if not name:
            continue
        retailer_count = group["retailer_id"].nunique()
        if retailer_count >= 2:
            exact_group_ids[name] = stable_id(name, prefix="grp")

    for idx, row in df.iterrows():
        name = row["normalized_name"]
        if name in exact_group_ids:
            df.at[idx, "candidate_group_id"] = exact_group_ids[name]
            df.at[idx, "match_method"] = "exact_normalized_name"
            df.at[idx, "match_confidence"] = 1.0

    # Fuzzy candidates are not promoted to a match group; they are only surfaced for review.
    # Compare normalized names without size tokens, but require a shared base and explicit
    # size compatibility where both products expose sizes.
    review_rows: list[dict[str, Any]] = []
    candidate_pairs: set[tuple[int, int]] = set()
    by_base: dict[str, list[int]] = {}
    for idx, row in df.iterrows():
        base = row["name_without_size"]
        if len(base) >= 8:
            by_base.setdefault(base, []).append(idx)

    for base, indices in by_base.items():
        if len(indices) < 2:
            continue
        group = df.loc[indices]
        if group["retailer_id"].nunique() < 2:
            continue
        for i in indices:
            for j in indices:
                if j <= i:
                    continue
                a, b = df.loc[i], df.loc[j]
                if a["retailer_id"] == b["retailer_id"]:
                    continue
                sa, sb = a["size_tokens"], b["size_tokens"]
                reason = "Tên giống sau khi bỏ thông tin dung tích/quy cách; cần xác minh"
                if sa and sb and sa != sb:
                    reason = "Tên gần giống nhưng dung tích/quy cách khác nhau"
                candidate_pairs.add((i, j))
                for row in (a, b):
                    review_rows.append({
                        "candidate_group_id": stable_id(base, prefix="review"),
                        "product_id": row["product_id"],
                        "retailer_id": row["retailer_id"],
                        "product_name": row["product_name"],
                        "product_url": row["product_url"],
                        "normalized_name": row["normalized_name"],
                        "candidate_group_size": len(indices),
                        "candidate_retailer_count": int(group["retailer_id"].nunique()),
                        "review_reason": reason,
                    })

    # Build one matching row per source product belonging to an exact cross-retailer group.
    # product_id points to the catalog record for that retailer; candidate_group_id is
    # recorded in match_id suffix so group identity is preserved without overwriting product_id.
    output_rows: list[dict[str, Any]] = []
    for _, row in df[df["candidate_group_id"].ne("")].iterrows():
        group_id = row["candidate_group_id"]
        match_id = stable_id(group_id, row["product_id"], row["retailer_id"], prefix="match")
        output_rows.append({
            "match_id": match_id,
            "match_group_id": group_id,
            "product_id": row["product_id"],
            "retailer_id": row["retailer_id"],
            "source_product_id": row["product_id"],
            "source_product_name": row["product_name"],
            "match_method": row["match_method"],
            "match_confidence": row["match_confidence"],
            "verified_by_human": False,
            "match_status": "pending",
        })

    matching = pd.DataFrame(output_rows, columns=OUTPUT_COLUMNS)
    if not matching.empty:
        matching = matching.drop_duplicates(subset=["match_id"]).sort_values(
            ["retailer_id", "source_product_name"], kind="stable"
        )

    review = pd.DataFrame(review_rows, columns=REVIEW_COLUMNS)
    if not review.empty:
        # One review row per catalog product per retailer. Combine reasons when the same
        # product was surfaced through multiple pair comparisons.
        review = (
            review.groupby(["product_id", "retailer_id"], as_index=False, dropna=False)
            .agg({
                "candidate_group_id": lambda values: "; ".join(sorted(set(map(str, values)))),
                "product_name": "first",
                "product_url": "first",
                "normalized_name": "first",
                "candidate_group_size": "max",
                "candidate_retailer_count": "max",
                "review_reason": lambda values: "; ".join(sorted(set(map(str, values)))),
            })
        )
        review = review.sort_values(["candidate_group_id", "retailer_id", "product_name"], kind="stable")

    return matching, review


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo candidate đối chiếu sản phẩm liên nhà bán lẻ.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.80,
        help="Giữ tham số tương thích CLI; bản này chỉ tự nhóm tên chuẩn hóa trùng khớp chính xác.",
    )
    args = parser.parse_args()
    if not 0 <= args.min_confidence <= 1:
        parser.error("--min-confidence phải nằm trong khoảng 0 đến 1.")

    products = load_products()
    if products.empty:
        raise RuntimeError("products.csv không có sản phẩm hợp lệ.")

    print(f"Catalog products loaded: {len(products)}", flush=True)
    print("Retailer counts:", flush=True)
    print(products.groupby("retailer_id").size().to_string(), flush=True)

    matching, review = build_candidate_groups(products, args.min_confidence)
    output_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    review_path = args.review_output if args.review_output.is_absolute() else PROJECT_ROOT / args.review_output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    matching.to_csv(output_path, index=False, encoding="utf-8-sig")
    review.to_csv(review_path, index=False, encoding="utf-8-sig")

    print(f"Cross-retailer exact-name candidates written: {len(matching)}", flush=True)
    print(f"Fuzzy/size review rows written: {len(review)}", flush=True)
    print(f"Matching output: {output_path}", flush=True)
    print(f"Review output: {review_path}", flush=True)
    print("All match_status values are pending; no matches were auto-confirmed.", flush=True)


if __name__ == "__main__":
    main()

