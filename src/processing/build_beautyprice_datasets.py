"""Build normalized BEAUTYPRICE product, category, and price-snapshot tables.

Place in: src/processing/build_beautyprice_datasets.py
Run from project root: python src/processing/build_beautyprice_datasets.py

Compatibility notes:
- Preserves existing price_snapshots.csv rows and existing product_id/snapshot_id values.
- Uses the legacy product_id formula for new products: stable_id(source.lower(), canonical_url).
- Keeps category outside price_snapshots, in product_categories.csv, so category changes
  never rewrite price history and a product can belong to more than one category.
- New snapshots append; same product + exact collected_at is one observation key.
- If the same observation key has conflicting values, it is not silently selected:
  the incoming conflict is logged and skipped. Existing history is preserved.
- Inputs that do not exist are optional and skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_DIR = PROJECT_ROOT / "output" / "reports"

# Generic multi-source / multi-category configuration.
# Add one entry per dataset; several entries may share the same retailer or category.
# Prefer QA outputs when they contain product_type; use fallback_path only if the QA
# file does not exist. Missing optional input files are skipped by load_inputs().
INPUTS = [
    {
        # Same pattern as cleansers: parser-generated QA dataset first, raw parser
        # output as fallback. hasaki_products_clean.csv is a legacy intermediate
        # and is no longer required by this normalized pipeline.
        "path": INTERIM_DIR / "hasaki" / "hasaki_sunscreens_qa.csv",
        "fallback_path": INTERIM_DIR / "hasaki" / "hasaki_sunscreens.csv",
        "source": "Hasaki",
        "category": "Kem chống nắng",
    },
    {
        "path": INTERIM_DIR / "hasaki" / "hasaki_cleansers_qa.csv",
        "fallback_path": INTERIM_DIR / "hasaki" / "hasaki_cleansers.csv",
        "source": "Hasaki",
        "category": "Sữa rửa mặt",
    },
    {
        # Serum: use parser QA output first so product_type is retained.
        "path": INTERIM_DIR / "hasaki" / "hasaki_serum_qa.csv",
        "fallback_path": INTERIM_DIR / "hasaki" / "hasaki_serum.csv",
        "source": "Hasaki",
        "category": "Serum",
    },
    {
        # Makeup remover category.
        "path": INTERIM_DIR / "hasaki" / "hasaki_tay_trang_qa.csv",
        "fallback_path": INTERIM_DIR / "hasaki" / "hasaki_tay_trang.csv",
        "source": "Hasaki",
        "category": "Tẩy trang mặt",
    },
    
    {
        # Sữa tắm
        "path": INTERIM_DIR / "hasaki" / "hasaki_body_wash_qa.csv",
        "fallback_path": INTERIM_DIR / "hasaki" / "hasaki_body_wash.csv",
        "source": "Hasaki",
        "category": "Sữa tắm",
    },
    
    {
        # Tẩy tế bào chết body
        "path": INTERIM_DIR / "hasaki" / "hasaki_exfoliators_qa.csv",
        "fallback_path": INTERIM_DIR / "hasaki" / "hasaki_exfoliators.csv",
        "source": "Hasaki",
        "category": "Tẩy tế bào chết body",
    },

    # Guardian: six categories added; existing Hasaki configuration above is unchanged.
    {
        "path": INTERIM_DIR / "guardian" / "guardian_sunscreens_qa.csv",
        "fallback_path": INTERIM_DIR / "guardian" / "guardian_sunscreens.csv",
        "source": "Guardian",
        "category": "Kem chống nắng",
    },
    {
        "path": INTERIM_DIR / "guardian" / "guardian_cleansers_qa.csv",
        "fallback_path": INTERIM_DIR / "guardian" / "guardian_cleansers.csv",
        "source": "Guardian",
        "category": "Sữa rửa mặt",
    },
    {
        "path": INTERIM_DIR / "guardian" / "guardian_serums_qa.csv",
        "fallback_path": INTERIM_DIR / "guardian" / "guardian_serums.csv",
        "source": "Guardian",
        "category": "Serum",
    },
    {
        "path": INTERIM_DIR / "guardian" / "guardian_tay_trang_qa.csv",
        "fallback_path": INTERIM_DIR / "guardian" / "guardian_tay_trang.csv",
        "source": "Guardian",
        "category": "Tẩy trang",
    },
    {
        "path": INTERIM_DIR / "guardian" / "guardian_exfoliators_qa.csv",
        "fallback_path": INTERIM_DIR / "guardian" / "guardian_exfoliators.csv",
        "source": "Guardian",
        "category": "Tẩy tế bào chết cơ thể",
    },
    {
        "path": INTERIM_DIR / "guardian" / "guardian_body_wash_qa.csv",
        "fallback_path": INTERIM_DIR / "guardian" / "guardian_body_wash.csv",
        "source": "Guardian",
        "category": "Sữa tắm",
    },

    # The Gioi Skin Food: six categories added; existing Hasaki and Guardian
    # configuration and build logic above/below remain unchanged.
    {
        "path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_sunscreens_qa.csv",
        "fallback_path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_sunscreens.csv",
        "source": "The Gioi Skin Food",
        "category": "Kem chống nắng",
    },
    {
        "path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_cleansers_qa.csv",
        "fallback_path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_cleansers.csv",
        "source": "The Gioi Skin Food",
        "category": "Sữa rửa mặt",
    },
    {
        "path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_serums_qa.csv",
        "fallback_path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_serums.csv",
        "source": "The Gioi Skin Food",
        "category": "Serum",
    },
    {
        "path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_tay_trang_qa.csv",
        "fallback_path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_tay_trang.csv",
        "source": "The Gioi Skin Food",
        "category": "Tẩy trang",
    },
    {
        "path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_exfoliators_qa.csv",
        "fallback_path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_exfoliators.csv",
        "source": "The Gioi Skin Food",
        "category": "Tẩy tế bào chết",
    },
    {
        "path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_body_wash_qa.csv",
        "fallback_path": INTERIM_DIR / "thegioiskinfood" / "thegioiskinfood_body_wash.csv",
        "source": "The Gioi Skin Food",
        "category": "Sữa tắm",
    },


    # Cocolux: six categories added; existing retailer configuration and build logic unchanged.
    {
        "path": INTERIM_DIR / "cocolux" / "cocolux_sunscreens_qa.csv",
        "fallback_path": INTERIM_DIR / "cocolux" / "cocolux_sunscreens.csv",
        "source": "Cocolux",
        "category": "Kem chống nắng",
    },
    {
        "path": INTERIM_DIR / "cocolux" / "cocolux_cleansers_qa.csv",
        "fallback_path": INTERIM_DIR / "cocolux" / "cocolux_cleansers.csv",
        "source": "Cocolux",
        "category": "Sữa rửa mặt",
    },
    {
        "path": INTERIM_DIR / "cocolux" / "cocolux_serum_qa.csv",
        "fallback_path": INTERIM_DIR / "cocolux" / "cocolux_serum.csv",
        "source": "Cocolux",
        "category": "Serum",
    },
    {
        "path": INTERIM_DIR / "cocolux" / "cocolux_tay_trang_qa.csv",
        "fallback_path": INTERIM_DIR / "cocolux" / "cocolux_tay_trang.csv",
        "source": "Cocolux",
        "category": "Tẩy trang",
    },
    {
        "path": INTERIM_DIR / "cocolux" / "cocolux_exfoliators_qa.csv",
        "fallback_path": INTERIM_DIR / "cocolux" / "cocolux_exfoliators.csv",
        "source": "Cocolux",
        "category": "Tẩy tế bào chết",
    },
    {
        "path": INTERIM_DIR / "cocolux" / "cocolux_body_wash_qa.csv",
        "fallback_path": INTERIM_DIR / "cocolux" / "cocolux_body_wash.csv",
        "source": "Cocolux",
        "category": "Sữa tắm",
    },

    # Watsons: six categories added; existing retailer configuration and build logic unchanged.
    {
        "path": INTERIM_DIR / "watsons" / "watsons_sunscreens_qa.csv",
        "fallback_path": INTERIM_DIR / "watsons" / "watsons_sunscreens.csv",
        "source": "Watsons",
        "category": "Kem chống nắng",
    },
    {
        "path": INTERIM_DIR / "watsons" / "watsons_cleansers_qa.csv",
        "fallback_path": INTERIM_DIR / "watsons" / "watsons_cleansers.csv",
        "source": "Watsons",
        "category": "Sữa rửa mặt",
    },
    {
        "path": INTERIM_DIR / "watsons" / "watsons_serums_qa.csv",
        "fallback_path": INTERIM_DIR / "watsons" / "watsons_serums.csv",
        "source": "Watsons",
        "category": "Serum",
    },
    {
        "path": INTERIM_DIR / "watsons" / "watsons_tay_trang_qa.csv",
        "fallback_path": INTERIM_DIR / "watsons" / "watsons_tay_trang.csv",
        "source": "Watsons",
        "category": "Tẩy trang",
    },
    {
        "path": INTERIM_DIR / "watsons" / "watsons_exfoliators_qa.csv",
        "fallback_path": INTERIM_DIR / "watsons" / "watsons_exfoliators.csv",
        "source": "Watsons",
        "category": "Tẩy tế bào chết",
    },
    {
        "path": INTERIM_DIR / "watsons" / "watsons_body_wash_qa.csv",
        "fallback_path": INTERIM_DIR / "watsons" / "watsons_body_wash.csv",
        "source": "Watsons",
        "category": "Sữa tắm",
    },

    # Add future retailers/categories by adding another config entry.
]

PRODUCTS_FILE = PROCESSED_DIR / "products.csv"
CATEGORIES_FILE = PROCESSED_DIR / "product_categories.csv"
SNAPSHOTS_FILE = PROCESSED_DIR / "price_snapshots.csv"
INPUT_REPORT_FILE = REPORT_DIR / "beautyprice_input_report.csv"
CONFLICT_REPORT_FILE = REPORT_DIR / "beautyprice_snapshot_conflicts.csv"

PRODUCT_COLUMNS = ["product_id", "retailer_id", "source", "product_name", "brand", "product_url", "product_type"]
CATEGORY_COLUMNS = ["product_id", "category", "source", "category_source_file"]
SNAPSHOT_COLUMNS = [
    "snapshot_id", "product_id", "retailer_id", "source", "current_price_vnd",
    "listed_price_vnd", "discount_percent", "rating", "review_count",
    "collected_at", "product_url", "source_file",
]
NUMERIC_COLUMNS = ["current_price_vnd", "listed_price_vnd", "discount_percent", "rating", "review_count"]
REQUIRED_PRODUCT_COLUMNS = {"product_url"}


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def stable_id(*parts: Any, prefix: str) -> str:
    raw = "|".join("" if is_missing(p) else str(p).strip() for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype={"product_url": "string"})


def canonicalize_url(value: Any) -> str | None:
    if is_missing(value):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return raw.rstrip("/") or None
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    tracking_keys = {"gclid", "fbclid", "ref", "source"}
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if k.lower() not in tracking_keys and not k.lower().startswith("utm_")]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def retailer_key(source: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", source.lower()).strip("_")


def clean_text(value: Any) -> str | None:
    if is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    """Load product/category catalog rows separately from rows eligible for price snapshots."""
    snapshots_parts: list[pd.DataFrame] = []
    products_parts: list[pd.DataFrame] = []
    category_parts: list[pd.DataFrame] = []
    reports: list[dict[str, Any]] = []

    for cfg in INPUTS:
        path = Path(cfg["path"])
        if not path.exists() and cfg.get("fallback_path"):
            path = Path(cfg["fallback_path"])

        report = {
            "input_file": str(path.relative_to(PROJECT_ROOT)),
            "source": cfg["source"],
            "category": cfg["category"],
            "rows_read": 0,
            "rows_usable": 0,
            "rows_missing_url": 0,
            "rows_missing_price": 0,
            "rows_missing_collected_at": 0,
            "rows_snapshot_eligible": 0,
            "status": "loaded",
        }
        if not path.exists():
            report["status"] = "not found; skipped (optional)"
            reports.append(report)
            continue

        df = read_csv(path)
        report["rows_read"] = len(df)
        missing = REQUIRED_PRODUCT_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"{path} thiếu cột bắt buộc cho catalog: {sorted(missing)}")

        df["source"] = str(cfg["source"]).strip()
        df["retailer_id"] = retailer_key(str(cfg["source"]).strip())
        df["category"] = str(cfg["category"]).strip()
        df["product_url"] = df["product_url"].map(canonicalize_url).astype("string")

        # Watsons QA files use current_price/listed_price instead of the
        # normalized *_vnd column names. Map only Watsons inputs so the
        # processing logic for other retailers remains unchanged.
        if str(cfg["source"]).strip().casefold() == "watsons":
            if "current_price_vnd" not in df.columns and "current_price" in df.columns:
                df["current_price_vnd"] = df["current_price"]
            if "listed_price_vnd" not in df.columns and "listed_price" in df.columns:
                df["listed_price_vnd"] = df["listed_price"]

        if "collected_at" not in df.columns:
            df["collected_at"] = pd.NA
        df["collected_at"] = df["collected_at"].map(clean_text).astype("string")

        for col in NUMERIC_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
            df[col] = pd.to_numeric(df[col], errors="coerce")

        for col in ("product_name", "brand"):
            if col not in df.columns:
                df[col] = pd.NA
            df[col] = df[col].map(clean_text)

        if "product_type" not in df.columns:
            df["product_type"] = pd.NA
        allowed_product_types = {"single", "multi_pack", "bundle", "unknown"}
        df["product_type"] = df["product_type"].map(
            lambda v: clean_text(v).lower() if clean_text(v) else None
        )
        invalid_types = df["product_type"].notna() & ~df["product_type"].isin(allowed_product_types)
        if invalid_types.any():
            bad = sorted(df.loc[invalid_types, "product_type"].dropna().unique().tolist())
            raise ValueError(
                f"{path} có product_type không hợp lệ: {bad}; "
                f"cho phép {sorted(allowed_product_types)}"
            )

        if "source_file" not in df.columns:
            df["source_file"] = path.name
        df["source_file"] = df["source_file"].fillna(path.name).astype("string")

        report["rows_missing_url"] = int((df["product_url"].isna() | df["product_url"].eq("")).sum())
        report["rows_missing_price"] = int(df["current_price_vnd"].isna().sum())
        report["rows_missing_collected_at"] = int(
            (df["collected_at"].isna() | df["collected_at"].eq("")).sum()
        )

        # Catalog eligibility: a stable product URL is sufficient.
        catalog_usable = df["product_url"].notna() & df["product_url"].ne("")
        catalog = df.loc[catalog_usable].copy()
        report["rows_usable"] = len(catalog)

        if not catalog.empty:
            catalog["product_id"] = catalog.apply(
                lambda r: stable_id(str(r["source"]).lower(), r["product_url"], prefix="prod"),
                axis=1,
            )
            catalog["category_source_file"] = path.name
            products_parts.append(catalog[PRODUCT_COLUMNS].copy())
            category_parts.append(
                catalog[["product_id", "category", "source", "category_source_file"]].copy()
            )

        # Snapshot eligibility is deliberately stricter than catalog eligibility.
        snapshot_usable = (
            catalog_usable
            & df["collected_at"].notna()
            & df["collected_at"].ne("")
            & df["current_price_vnd"].notna()
        )
        valid_snapshots = df.loc[snapshot_usable].copy()
        report["rows_snapshot_eligible"] = len(valid_snapshots)

        if not valid_snapshots.empty:
            valid_snapshots["product_id"] = valid_snapshots.apply(
                lambda r: stable_id(str(r["source"]).lower(), r["product_url"], prefix="prod"),
                axis=1,
            )
            valid_snapshots["snapshot_id"] = valid_snapshots.apply(
                lambda r: stable_id(
                    r["product_id"], r["retailer_id"], r["collected_at"], prefix="snap"
                ),
                axis=1,
            )
            snapshots_parts.append(valid_snapshots[SNAPSHOT_COLUMNS].copy())

        # Record every existing input in the report, even if it has no snapshot-eligible rows.
        reports.append(report)

    snapshots = pd.concat(snapshots_parts, ignore_index=True) if snapshots_parts else pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    products = pd.concat(products_parts, ignore_index=True) if products_parts else pd.DataFrame(columns=PRODUCT_COLUMNS)
    categories = pd.concat(category_parts, ignore_index=True) if category_parts else pd.DataFrame(columns=CATEGORY_COLUMNS)
    return snapshots, products, categories, reports


def compare_value(value: Any) -> str:
    return "<NA>" if is_missing(value) else str(value).strip()


def merge_snapshots(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Append new observations, preserve existing rows, and report same-key conflicts."""
    existing = existing.copy()
    for col in SNAPSHOT_COLUMNS:
        if col not in existing.columns:
            existing[col] = pd.NA
    existing = existing[SNAPSHOT_COLUMNS]
    conflicts: list[dict[str, Any]] = []

    # Recompute incoming IDs using same keys; existing IDs are retained as-is for history.
    combined = pd.concat([existing, incoming[SNAPSHOT_COLUMNS]], ignore_index=True)
    compare_cols = ["current_price_vnd", "listed_price_vnd", "discount_percent", "rating", "review_count", "product_url", "source"]
    kept_indices: list[int] = []
    for sid, group in combined.groupby("snapshot_id", sort=False, dropna=False):
        if is_missing(sid):
            # Rows without a snapshot key cannot be safely deduplicated.
            for idx in group.index:
                kept_indices.append(idx)
            continue
        if len(group) == 1:
            kept_indices.append(group.index[0])
            continue
        signatures = group[compare_cols].apply(lambda col: col.map(compare_value)).agg("|".join, axis=1)
        if signatures.nunique(dropna=False) == 1:
            # Same snapshot, same facts: keep the earliest (existing) row.
            kept_indices.append(group.index[0])
        else:
            # Existing row wins for an already-known key; new conflicts are logged and skipped.
            existing_indices = [i for i in group.index if i < len(existing)]
            if existing_indices:
                kept_indices.append(existing_indices[0])
            else:
                # If all conflicting rows are new, don't choose an arbitrary price.
                pass
            for _, row in group.iterrows():
                rec = row.to_dict()
                rec["conflict_reason"] = "same snapshot_id (product + retailer + collected_at) but values differ"
                conflicts.append(rec)
    merged = combined.loc[sorted(set(kept_indices))].copy()
    merged = merged.drop_duplicates(subset=["snapshot_id"], keep="first")
    conflict_df = pd.DataFrame(conflicts, columns=SNAPSHOT_COLUMNS + ["conflict_reason"])
    return merged, conflict_df


def merge_products(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Merge product attributes without changing snapshot history; prefer non-empty incoming fields."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    # Key is retailer_id + canonical product URL; category intentionally isn't here.
    for df, incoming_rows in ((existing, False), (incoming, True)):
        if df.empty:
            continue
        for _, row in df.iterrows():
            source = clean_text(row.get("source")) or ""
            url = canonicalize_url(row.get("product_url"))
            if not url:
                continue
            rid = clean_text(row.get("retailer_id")) or retailer_key(source)
            pid = clean_text(row.get("product_id")) or stable_id(source.lower(), url, prefix="prod")
            key = (rid, url)
            record = rows.setdefault(key, {"product_id": pid, "retailer_id": rid, "source": source,
                                           "product_name": None, "brand": None, "product_url": url,
                                           "product_type": None})
            # Preserve established product ID if there is one; never mutate historical identity.
            if not record.get("product_id"):
                record["product_id"] = pid
            for field in ("source", "product_name", "brand", "product_type"):
                value = clean_text(row.get(field))
                if value and (incoming_rows or not record.get(field)):
                    record[field] = value
    out = pd.DataFrame(rows.values(), columns=PRODUCT_COLUMNS)
    return out.sort_values(["source", "product_name"], na_position="last").reset_index(drop=True) if not out.empty else out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build normalized BEAUTYPRICE tables. By default, rebuilding metadata does not append price snapshots."
    )
    parser.add_argument(
        "--append-snapshots",
        action="store_true",
        help="Append eligible price observations from configured inputs. Use only when intentionally starting/updating price history."
    )
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    incoming_snapshots, incoming_products, incoming_categories, input_reports = load_inputs()

    # Existing snapshots are authoritative. Rebuilding product/category tables must not
    # automatically create another observation from a static interim CSV.
    if SNAPSHOTS_FILE.exists():
        existing_snapshots = read_csv(SNAPSHOTS_FILE)
    else:
        existing_snapshots = pd.DataFrame(columns=SNAPSHOT_COLUMNS)

    if args.append_snapshots:
        # Explicit opt-in only: never create or append price history during a catalog build.
        merged_snapshots, conflicts = merge_snapshots(existing_snapshots, incoming_snapshots)
    else:
        # Catalog-only default: preserve current snapshot history, and do not initialize
        # it from static parser CSVs even on the first build.
        merged_snapshots = existing_snapshots.copy()
        for col in SNAPSHOT_COLUMNS:
            if col not in merged_snapshots.columns:
                merged_snapshots[col] = pd.NA
        merged_snapshots = merged_snapshots[SNAPSHOT_COLUMNS]
        conflicts = pd.DataFrame(columns=SNAPSHOT_COLUMNS + ["conflict_reason"])

    # Product table is built from current input attributes plus existing snapshot keys.
    existing_product_rows = existing_snapshots.copy()
    if not existing_product_rows.empty:
        # Tolerate older snapshot schemas by adding metadata columns that may not
        # have existed when historical snapshots were first created.
        for col in PRODUCT_COLUMNS:
            if col not in existing_product_rows.columns:
                existing_product_rows[col] = pd.NA
        if "source" not in existing_product_rows.columns:
            existing_product_rows["source"] = pd.NA
        if "retailer_id" not in existing_product_rows.columns:
            existing_product_rows["retailer_id"] = existing_product_rows["source"].map(
                lambda value: retailer_key(clean_text(value) or "")
            )
        existing_products = existing_product_rows[PRODUCT_COLUMNS].copy()
    else:
        existing_products = pd.DataFrame(columns=PRODUCT_COLUMNS)
    products = merge_products(existing_products, incoming_products)

    # Keep known historical categories; merge new category assignments without duplicates.
    category_rows = []
    if CATEGORIES_FILE.exists():
        old_categories = read_csv(CATEGORIES_FILE)
        for col in CATEGORY_COLUMNS:
            if col not in old_categories.columns:
                old_categories[col] = pd.NA
        category_rows.append(old_categories[CATEGORY_COLUMNS])
    if not incoming_categories.empty:
        category_rows.append(incoming_categories[CATEGORY_COLUMNS])
    categories = pd.concat(category_rows, ignore_index=True) if category_rows else pd.DataFrame(columns=CATEGORY_COLUMNS)
    if not categories.empty:
        categories["category"] = categories["category"].map(clean_text)
        categories = categories[categories["product_id"].notna() & categories["category"].notna()]
        categories = categories.drop_duplicates(subset=["product_id", "category"], keep="last")

    # Referential-integrity checks: stop before writing if category/snapshot rows point
    # to products that are not present in the merged products table.
    product_ids = set(products["product_id"].dropna().astype(str))
    orphan_categories = categories.loc[~categories["product_id"].astype(str).isin(product_ids)] if not categories.empty else categories
    orphan_snapshots = merged_snapshots.loc[~merged_snapshots["product_id"].astype(str).isin(product_ids)] if not merged_snapshots.empty else merged_snapshots
    if not orphan_categories.empty or not orphan_snapshots.empty:
        details = []
        if not orphan_categories.empty:
            details.append(f"{len(orphan_categories)} category links reference missing product_id")
        if not orphan_snapshots.empty:
            details.append(f"{len(orphan_snapshots)} snapshots reference missing product_id")
        raise ValueError("Referential-integrity check failed; no output tables were written: " + "; ".join(details))

    pd.DataFrame(input_reports).to_csv(INPUT_REPORT_FILE, index=False, encoding="utf-8-sig")
    if conflicts.empty:
        conflicts = pd.DataFrame(columns=SNAPSHOT_COLUMNS + ["conflict_reason"])
    conflicts.to_csv(CONFLICT_REPORT_FILE, index=False, encoding="utf-8-sig")

    # Write only after all datasets have been built successfully.
    products.to_csv(PRODUCTS_FILE, index=False, encoding="utf-8-sig")
    categories.to_csv(CATEGORIES_FILE, index=False, encoding="utf-8-sig")
    merged_snapshots.to_csv(SNAPSHOTS_FILE, index=False, encoding="utf-8-sig")

    print("BEAUTYPRICE NORMALIZED DATASETS BUILT")
    print("Snapshot mode:", "append incoming observations (explicit opt-in)" if args.append_snapshots else "catalog-only; preserve existing history")
    print(f"Input files configured: {len(INPUTS)}")
    print(f"Input files loaded: {sum(r['status'] == 'loaded' for r in input_reports)}")
    for report in input_reports:
        print(f"- {report['input_file']}: {report['status']}; catalog rows usable={report['rows_usable']}; snapshot-eligible={report.get('rows_snapshot_eligible', 0)}")
    print(f"Products saved: {len(products):,}")
    if "product_type" in products.columns:
        typed = products["product_type"].fillna("not classified").value_counts(dropna=False)
        print("Product type counts:")
        for label, count in typed.items():
            print(f"  - {label}: {count:,}")
    print(f"Product-category links saved: {len(categories):,}")
    print(f"Referential integrity: passed (categories/snapshots reference existing products)")
    print(f"Price snapshots saved: {len(merged_snapshots):,}")
    print(f"Snapshot conflicts logged: {len(conflicts):,}")
    print(f"Products table: {PRODUCTS_FILE}")
    print(f"Product categories table: {CATEGORIES_FILE}")
    print(f"Price snapshots table: {SNAPSHOTS_FILE}")
    print(f"Input report: {INPUT_REPORT_FILE}")
    print(f"Conflict report: {CONFLICT_REPORT_FILE}")


if __name__ == "__main__":
    main()



