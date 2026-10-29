"""
Reusable Guardian review QA + cleaning pipeline for BEAUTYPRICE_INTELLIGENCE.

- Tham khảo cấu trúc clean_hasaki_reviews_v2_all_categories.py.
- Không sửa collector hoặc file CSV raw.
- Mặc định xử lý 6 danh mục review Guardian.
- Xuất *_clean.csv, *_review_audit.csv và review_quality_report.csv.
- Không so sánh source_product_id của Guardian với đuôi URL: đây thường là Magento entity ID,
  không phải ID nằm trong slug URL.
- Xóa cột định danh người đánh giá và che thông tin liên hệ trong nội dung.

Chạy từ thư mục gốc dự án:
    python src/processors/clean_guardian_reviews.py
    python src/processors/clean_guardian_reviews.py --input data/interim/guardian/by_category/sua_tam_reviews.csv
    python src/processors/clean_guardian_reviews.py --input file1.csv --input file2.csv
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "guardian_reviews"
GUARDIAN_INPUT_DIR = PROJECT_ROOT / "data" / "interim" / "guardian" / "by_category"

# Sáu danh mục đang triển khai cho Guardian.
DEFAULT_INPUTS = [
    GUARDIAN_INPUT_DIR / "kem_chong_nang_reviews.csv",
    GUARDIAN_INPUT_DIR / "sua_rua_mat_reviews.csv",
    GUARDIAN_INPUT_DIR / "serum_reviews.csv",
    GUARDIAN_INPUT_DIR / "tay_trang_reviews.csv",
    GUARDIAN_INPUT_DIR / "sua_tam_reviews.csv",
    GUARDIAN_INPUT_DIR / "tay_te_bao_chet_reviews.csv",
]

ALIASES = {
    "review_id": ["review_id", "id", "rating_id", "comment_id", "amreview_id"],
    "requested_product_id": ["requested_product_id", "requested_guardian_id", "product_id_requested"],
    "source_product_id": ["source_product_id", "actual_product_id", "guardian_product_id", "guardian_entity_id"],
    "product_id": ["product_id"],
    "product_name": ["product_name", "name", "source_product_name", "product_title"],
    "content": ["content", "review_content", "review_text", "comment", "text", "review", "description"],
    "rating": ["rating", "star", "rating_star", "score", "rating_value"],
    "created_at": ["created_at", "review_date", "date", "created", "timestamp"],
    "product_url": ["product_url", "url", "source_url"],
    "category": ["category", "product_category"],
}

PHONE_RE = re.compile(r"(?<!\w)(?:\+?84[\s.-]?)?(?:0\d{8,10})(?!\w)")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
HTML_TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
SELLING_TERMS = [
    "pass", "thanh lý", "thanh ly", "ai mua", "liên hệ mình", "lien he minh",
    "zalo", "ib mình", "ib minh", "inbox", "mình bán", "minh ban",
    "cần pass", "can pass", "check hàng", "check hang",
]
PRICE_TERMS = [
    "giá sao", "gia sao", "sao lại", "sao lai", "giá bao nhiêu", "gia bao nhieu",
    "giá web", "gia web", "mua tới", "mua toi", "cửa hàng", "cua hang",
]
LOW_INFO = {
    "test", "đẹp", "dep", "ok", "tốt", "tot", "good", "nice", "10đ", "10d",
    "chưa sử dụng", "chua su dung", "chưa dùng", "chua dung",
}
PRIVATE_COLUMNS = {
    "user_fullname", "fullname", "user_name", "username", "user_id",
    "reviewer_name", "reviewer_id", "reviewer", "phone", "email", "mobile",
    "author_name", "author_id",
}


def norm_col(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def find_col(df: pd.DataFrame, logical: str) -> str | None:
    by_normalized = {norm_col(c): c for c in df.columns}
    for alias in ALIASES[logical]:
        found = by_normalized.get(norm_col(alias))
        if found is not None:
            return found
    return None


def read_csv_safely(path: Path) -> pd.DataFrame:
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"Không đọc được encoding của {path}: {last_error}")


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = HTML_TAG_RE.sub(" ", text)
    text = URL_RE.sub("[URL]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return SPACE_RE.sub(" ", text).strip()


def norm_id(value: Any) -> str:
    value = "" if value is None else str(value).strip()
    if not value:
        return ""
    match = re.fullmatch(r"(?:prod_)?(\d+)", value, flags=re.I)
    return match.group(1) if match else value


def classify_content(text: str) -> tuple[str, str]:
    value = text.strip()
    folded = value.casefold()
    if not value:
        return "empty", "exclude_from_analysis"
    if len(value) < 4 or folded in LOW_INFO:
        return "low_information", "manual_review_or_exclude"
    if any(term in folded for term in SELLING_TERMS):
        return "selling_or_spam", "manual_review_or_exclude"
    if any(term in folded for term in PRICE_TERMS):
        return "purchase_or_price_question", "keep_if_relevant"
    if len(value) < 12:
        return "short", "manual_review"
    return "usable_candidate", "keep_pending_manual_review"


def process_file(input_path: Path, output_dir: Path) -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_path}")

    raw = read_csv_safely(input_path)
    if raw.empty:
        raise ValueError(f"File không có dòng dữ liệu: {input_path}")

    cols = {name: find_col(raw, name) for name in ALIASES}
    content_col = cols["content"]
    if not content_col:
        raise ValueError(
            f"{input_path.name}: không tìm thấy cột nội dung review. "
            f"Cột hiện có: {list(raw.columns)}"
        )

    req_col = cols["requested_product_id"] or cols["product_id"]
    actual_col = cols["source_product_id"]
    review_id_col = cols["review_id"]

    work = raw.copy()
    work["source_file"] = input_path.name
    work["requested_product_id_normalized"] = (
        work[req_col].map(norm_id) if req_col else ""
    )
    work["actual_product_id_normalized"] = (
        work[actual_col].map(norm_id) if actual_col else ""
    )

    # Chỉ so sánh ID khi file có cả ID được yêu cầu và ID thực tế riêng biệt.
    # Với collector Guardian hiện tại, source_product_id là Magento entity ID,
    # không nên so với phần số trong URL sản phẩm.
    if req_col and actual_col and req_col != actual_col:
        expected_ids = work["requested_product_id_normalized"]
        actual_ids = work["actual_product_id_normalized"]
        work["product_id_match"] = [
            "unknown" if not str(e).strip() or not str(a).strip()
            else ("match" if norm_id(e) == norm_id(a) else "mismatch")
            for e, a in zip(expected_ids, actual_ids)
        ]
    else:
        work["product_id_match"] = "unknown"

    work["review_id_normalized"] = (
        work[review_id_col].astype(str).str.strip() if review_id_col else ""
    )
    work["content_original_length"] = work[content_col].astype(str).str.len()
    work["content_clean"] = work[content_col].map(clean_text)
    classified = work["content_clean"].map(classify_content)
    work["content_quality"] = classified.map(lambda x: x[0])
    work["suggested_action"] = classified.map(lambda x: x[1])

    # Khử trùng theo source product ID + review ID; nếu thiếu review ID,
    # dùng ID sản phẩm + nội dung đã làm sạch.
    dedup_product = work["actual_product_id_normalized"]
    if not dedup_product.astype(str).str.strip().ne("").any():
        dedup_product = work["requested_product_id_normalized"]
    if review_id_col and work["review_id_normalized"].astype(str).str.strip().ne("").any():
        ids = work["review_id_normalized"]
        keys = dedup_product.astype(str) + "||" + ids.astype(str)
        work["is_duplicate"] = ids.ne("") & keys.duplicated(keep="first")
    else:
        keys = dedup_product.astype(str) + "||" + work["content_clean"].str.casefold()
        work["is_duplicate"] = work["content_clean"].ne("") & keys.duplicated(keep="first")

    work["exclude_reason"] = ""
    work.loc[work["product_id_match"] == "mismatch", "exclude_reason"] = "product_id_mismatch"
    work.loc[work["is_duplicate"], "exclude_reason"] = work.loc[
        work["is_duplicate"], "exclude_reason"
    ].map(lambda x: (x + ";duplicate").strip(";"))
    work.loc[work["content_quality"] == "empty", "exclude_reason"] = work.loc[
        work["content_quality"] == "empty", "exclude_reason"
    ].map(lambda x: (x + ";empty_content").strip(";"))

    analysis = work[
        (work["product_id_match"] != "mismatch")
        & (~work["is_duplicate"])
        & (work["content_quality"] != "empty")
    ].copy()

    # Xuất nội dung đã làm sạch; giữ nguyên file raw.
    analysis[content_col] = analysis["content_clean"]
    audit = work.copy()
    audit[content_col] = audit["content_clean"]

    private_cols = [c for c in work.columns if norm_col(c) in PRIVATE_COLUMNS]
    analysis = analysis.drop(
        columns=[c for c in private_cols if c in analysis.columns], errors="ignore"
    )
    audit = audit.drop(
        columns=[c for c in private_cols if c in audit.columns], errors="ignore"
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    clean_path = output_dir / f"{stem}_clean.csv"
    audit_path = output_dir / f"{stem}_review_audit.csv"
    analysis.to_csv(clean_path, index=False, encoding="utf-8-sig")
    audit.to_csv(audit_path, index=False, encoding="utf-8-sig")

    return {
        "source": "guardian",
        "input_file": str(input_path),
        "rows_input": len(raw),
        "rows_analysis_output": len(analysis),
        "rows_product_id_mismatch": int((work["product_id_match"] == "mismatch").sum()),
        "rows_product_id_unknown": int((work["product_id_match"] == "unknown").sum()),
        "rows_duplicate": int(work["is_duplicate"].sum()),
        "rows_empty_content": int((work["content_quality"] == "empty").sum()),
        "rows_low_information": int((work["content_quality"] == "low_information").sum()),
        "rows_selling_or_spam_flagged": int((work["content_quality"] == "selling_or_spam").sum()),
        "rows_price_question_flagged": int((work["content_quality"] == "purchase_or_price_question").sum()),
        "rows_short_flagged": int((work["content_quality"] == "short").sum()),
        "rows_usable_candidate": int((work["content_quality"] == "usable_candidate").sum()),
        "clean_file": str(clean_path),
        "audit_file": str(audit_path),
        "note": "Cờ chất lượng chỉ là gợi ý; cần rà soát thủ công trước khi dùng cho NLP.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="QA + làm sạch review Guardian cho 6 danh mục; không sửa file raw."
    )
    parser.add_argument(
        "--input", action="append", default=None,
        help="CSV review đầu vào; dùng lặp --input để xử lý nhiều danh mục.",
    )
    parser.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR),
        help="Thư mục xuất dữ liệu sạch, audit và báo cáo.",
    )
    args = parser.parse_args()

    inputs = [Path(p).expanduser() for p in args.input] if args.input else DEFAULT_INPUTS
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = (Path.cwd() / output_dir).resolve()

    reports = []
    failures = 0
    print("=== GUARDIAN REVIEW QA + CLEANING ===")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Output dir:   {output_dir}")

    for input_path in inputs:
        if not input_path.is_absolute():
            input_path = (Path.cwd() / input_path).resolve()
        try:
            result = process_file(input_path, output_dir)
            reports.append(result)
            print(f"\n[OK] {input_path}")
            print(f"  Input rows:       {result['rows_input']}")
            print(f"  Analysis rows:    {result['rows_analysis_output']}")
            print(f"  ID mismatches:    {result['rows_product_id_mismatch']}")
            print(f"  ID unknown:       {result['rows_product_id_unknown']}")
            print(f"  Duplicates:       {result['rows_duplicate']}")
            print(f"  Clean file:       {result['clean_file']}")
            print(f"  Audit file:       {result['audit_file']}")
        except Exception as exc:
            failures += 1
            print(f"\n[ERROR] {input_path}: {exc}", file=sys.stderr)

    if reports:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "review_quality_report.csv"
        pd.DataFrame(reports).to_csv(report_path, index=False, encoding="utf-8-sig")
        print(f"\nQuality report: {report_path}")

    print(f"\nHoàn tất: {len(reports)} file thành công, {failures} file lỗi.")
    if not reports:
        print(
            "Kiểm tra lại đường dẫn đầu vào. Nếu tên file khác, dùng --input <đường_dẫn_csv>.",
            file=sys.stderr,
        )
    return 0 if reports and failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

