"""Kiểm tra CSDL sau import và đối chiếu kết quả truy vấn với phép tính độc lập.

    1. Số bản ghi: đếm lại từ CSV (dataset/raw + dataset/crawl/*) theo đúng quy tắc import, so với từng bảng trong CSDL.
    2. Truy vấn: chạy từng truy vấn trong queries.sql, rồi tính lại CÙNG kết quả bằng Python thuần đọc thẳng từ CSV
       (không dùng SQL), so khớp từng giá trị.

Chạy:  python verify_database.py      -> in kết quả + ghi reports/KIEM_TRA_CSDL.md
Chỉ dùng thư viện chuẩn của Python.
"""
import csv
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "dataset" / "raw"
CRAWL = ROOT / "dataset" / "crawl"
DB_PATH = Path(os.environ.get("BEAUTY_DB", ROOT / "dataset" / "beautyprice.db"))
QUERIES = Path(__file__).with_name("queries.sql")
REPORT = ROOT / "reports" / "KIEM_TRA_CSDL.md"
VALID_CATEGORIES = {"Kem chống nắng", "Serum", "Sữa rửa mặt", "Sữa tắm", "Tẩy trang", "Tẩy tế bào chết"}


# ---------------------------------------------------------------- đọc CSV (độc lập với build_database.py)

def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def first(pattern):
    return sorted(RAW.rglob(pattern))[0]


def price(value):
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def load_clean_data(imported_runs):
    """Dữ liệu sạch dùng để tính độc lập: sản phẩm, snapshot giá, review, danh mục, matching, nhật ký.
    Chỉ tính các lần crawler mà CSDL đã nạp (ghi trong etl_log); mặc định CSDL chỉ có dữ liệu gốc."""
    crawl_runs = sorted(CRAWL / r for r in imported_runs if (CRAWL / r / "snapshots.csv").exists())
    # đợt nạp không thêm sản phẩm mới (mặc định) -> bỏ qua snapshot của sản phẩm chưa có
    products = {}                              # product_id -> retailer_id
    for r in rows(first("products*.csv")):
        if r["product_id"].strip() and r["product_name"].strip():
            products.setdefault(r["product_id"].strip(), r["retailer_id"].strip().lower())
    raw_product_ids = set(products)

    snapshots = []                             # (product_id, collected_at, price, listed), theo thứ tự nạp
    seen = set()
    for r in rows(first("price_snapshots*.csv")):
        pid, p = r["product_id"].strip(), price(r["current_price_vnd"])
        if pid in products and p and r["snapshot_id"] not in seen:
            seen.add(r["snapshot_id"])
            snapshots.append((pid, r["collected_at"].strip(), p, price(r["listed_price_vnd"])))
    raw_snapshot_count = len(snapshots)

    crawl_pairs, crawl_logs, crawl_snapshots = set(), 0, 0
    for run in crawl_runs:
        for r in rows(run / "snapshots.csv"):
            pid = r["product_id"]
            if pid not in products and not imported_runs[run.name]:
                continue
            products.setdefault(pid, r["retailer_id"])
            snapshots.append((pid, r["collected_at"], price(r["current_price_vnd"]), price(r["listed_price_vnd"])))
            crawl_snapshots += 1
            if imported_runs[run.name]:  # nhãn danh mục chỉ được nạp ở đợt cho phép thêm sản phẩm mới
                crawl_pairs |= {(pid, c) for c in r["categories"].split(";") if c in VALID_CATEGORIES}
        if (run / "collection_log.csv").exists():
            crawl_logs += len(rows(run / "collection_log.csv"))

    pairs = {(r["product_id"].strip(), r["category"].strip()) for r in rows(first("product_categories (*).csv"))
             if r["product_id"].strip() in raw_product_ids and r["category"].strip() in VALID_CATEGORIES}

    reviews, keys = [], set()
    for path in sorted(RAW.rglob("*_reviews.csv")):
        source = path.name.split("_")[0]
        for r in rows(path):
            try:
                rating = float(r["rating"])
            except ValueError:
                continue
            key = (source, r["source_product_id"].strip(), r["review_id"].strip())
            if not key[1] or not key[2] or not 1 <= rating <= 5 or key in keys or r.get("is_duplicate", "").lower() in ("true", "1", "yes"):
                continue
            keys.add(key)
            bought = r.get("is_bought", "").strip().lower()
            reviews.append((source, round(rating, 1), 1 if bought in ("true", "1", "yes") else 0 if bought in ("false", "0", "no") else None))

    for run in crawl_runs:  # review thu thập thêm bằng crawler (Hasaki, kèm tên rút gọn)
        if (run / "reviews.csv").exists():
            for r in rows(run / "reviews.csv"):
                key = (r["source"], r["source_product_id"], r["review_id"])
                try:
                    rating = round(float(r["rating"]), 1)
                except ValueError:
                    continue
                if all(key) and 1 <= rating <= 5 and key not in keys:
                    keys.add(key)
                    reviews.append((r["source"], rating, int(float(r["is_bought"])) if r["is_bought"] not in ("", None) else None))

    matching = sum(1 for r in rows(first("product_matching.csv")) if r["match_id"].strip() and r["product_id"].strip() in raw_product_ids)
    return {
        "products": products, "snapshots": snapshots, "reviews": reviews, "crawl_runs": [p.name for p in crawl_runs],
        "counts": {
            "retailers": len(rows(first("retailers.csv"))),
            "products": len(products),
            "product_categories": len(pairs | crawl_pairs),
            "price_snapshots": raw_snapshot_count + crawl_snapshots,
            "reviews": len(reviews),
            "product_matching": matching,
            "collection_logs": len(rows(first("collection_logs.csv"))) + crawl_logs,
        },
    }


def latest_by_product(data):
    """Giá mới nhất của mỗi sản phẩm (cùng thời điểm thì bản ghi nạp sau thắng), áp quy tắc làm sạch giá niêm yết."""
    latest = {}
    for pid, collected_at, p, listed in data["snapshots"]:
        if pid not in latest or collected_at >= latest[pid][0]:
            listed = listed if listed and listed >= p else None
            latest[pid] = (collected_at, p, round((listed - p) / listed * 100, 2) if listed else None)
    return latest


# ---------------------------------------------------------------- phép tính độc lập cho từng truy vấn

def independent_results(data):
    products, latest = data["products"], latest_by_product(data)
    items = [(pid, products[pid], v[1], v[2]) for pid, v in latest.items()]  # (id, retailer, giá, % giảm)
    by_retailer = defaultdict(list)
    for pid, retailer, p, _ in items:
        by_retailer[retailer].append(p)
    per_day = defaultdict(int)
    for pid, collected_at, _, _ in data["snapshots"]:
        per_day[(collected_at[:10], products[pid])] += 1
    per_source = defaultdict(list)
    for source, rating, bought in data["reviews"]:
        per_source[source].append((rating, bought))
    return {
        "Q1_find_filter_projection": sorted(((pid, p) for pid, r, p, _ in items if r == "guardian" and p > 1_000_000), key=lambda x: (-x[1], x[0])),
        "Q2_sort_limit": sorted(((pid, r, p) for pid, r, p, _ in items), key=lambda x: (-x[2], x[0]))[:10],
        "Q3_aggregate_by_retailer": [(r, len(v), min(v), max(v), round(sum(v) / len(v), 2)) for r, v in sorted(by_retailer.items())],
        "Q4_filter_count_discount": sorted((r, n) for r, n in _count(r for _, r, _, d in items if d is not None and d > 30).items()),
        "Q5_aggregate_snapshots_by_day": [(d, r, n) for (d, r), n in sorted(per_day.items())],
        "Q6_aggregate_reviews": [(s, len(v), round(sum(x[0] for x in v) / len(v), 4), sum(1 for x in v if x[1] == 1),
                                  sum(1 for x in v if x[1] is not None)) for s, v in sorted(per_source.items())],
    }


def _count(values):
    result = defaultdict(int)
    for v in values:
        result[v] += 1
    return result


# Cột SQL tương ứng với bộ giá trị tính độc lập.
PROJECTIONS = {
    "Q1_find_filter_projection": lambda r: (r["product_id"], r["current_price_vnd"]),
    "Q2_sort_limit": lambda r: (r["product_id"], r["retailer_id"], r["current_price_vnd"]),
    "Q3_aggregate_by_retailer": lambda r: (r["retailer_id"], r["so_sp"], r["gia_min"], r["gia_max"], r["gia_tb"]),
    "Q4_filter_count_discount": lambda r: (r["retailer_id"], r["so_sp"]),
    "Q5_aggregate_snapshots_by_day": lambda r: (r["ngay"], r["retailer_id"], r["so_snapshot"]),
    "Q6_aggregate_reviews": lambda r: (r["source"], r["so_review"], r["diem_tb"], r["da_mua"], r["co_thong_tin"]),
}


def same(a, b):
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        for u, v in zip(x, y):
            if isinstance(u, float) or isinstance(v, float):
                if abs(float(u) - float(v)) > 1e-6:
                    return False
            elif u != v:
                return False
    return True


def parse_queries():
    text = QUERIES.read_text(encoding="utf-8")
    blocks = re.split(r"^-- name: (\S+)\s*$", text, flags=re.M)[1:]
    return {name: body.strip() for name, body in zip(blocks[::2], blocks[1::2])}


# ---------------------------------------------------------------- chạy kiểm tra + báo cáo

def main():
    if not DB_PATH.exists():
        sys.exit(f"Chưa có CSDL {DB_PATH}. Chạy build_database.py trước.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    imported = {m[1]: (new or 0) > 0 for step, new in conn.execute("SELECT step, rows_affected FROM etl_log")
                if (m := re.match(r"Nạp lần thu thập (crawl_\S+) \(crawler\)", step))}
    data = load_clean_data(imported)
    lines, ok_all = [], True

    print("1. Số bản ghi sau import (CSV sạch -> CSDL)")
    count_rows = []
    for table, expected in data["counts"].items():
        actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        ok = actual == expected
        ok_all &= ok
        count_rows.append((table, expected, actual, ok))
        print(f"   {table:<20} CSV={expected:<7} CSDL={actual:<7} {'PASS' if ok else 'FAIL'}")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_errors = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    ok_all &= integrity == "ok" and fk_errors == 0
    print(f"   integrity_check={integrity}, lỗi khóa ngoại={fk_errors}")

    print("2. Đối chiếu truy vấn (SQL vs Python độc lập)")
    expected = independent_results(data)
    query_rows = []
    for name, sql in parse_queries().items():
        result = [dict(r) for r in conn.execute(sql).fetchall()]
        if name in PROJECTIONS:
            ok = same([PROJECTIONS[name](r) for r in result], expected[name])
            ok_all &= ok
            status = "PASS" if ok else "FAIL"
        else:
            status = "Chỉ minh họa"
        query_rows.append((name, len(result), status, result[:5]))
        print(f"   {name:<34} {len(result):>4} dòng  {status}")

    write_report(data, count_rows, integrity, fk_errors, query_rows, ok_all)
    print(f"\nKẾT LUẬN: {'TẤT CẢ PASS' if ok_all else 'CÓ MỤC FAIL'} -> {REPORT.relative_to(ROOT)}")
    sys.exit(0 if ok_all else 1)


def write_report(data, count_rows, integrity, fk_errors, query_rows, ok_all):
    fmt = lambda v: f"{v:,.2f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".") if isinstance(v, float) else (f"{v:,}".replace(",", ".") if isinstance(v, int) else str(v))
    out = [
        "# Kết quả kiểm tra CSDL (Giai đoạn 5)",
        "",
        f"- **Chạy lúc:** {datetime.now():%d/%m/%Y %H:%M}. Script: `source-code/pipeline/verify_database.py`; truy vấn: `source-code/pipeline/queries.sql`.",
        "- **Nguồn đối chiếu:** CSV trong `dataset/raw/`" + (f" và các lần thu thập {', '.join(data['crawl_runs'])}" if data["crawl_runs"] else "") + ".",
        "- **Cách đối chiếu:** phép tính độc lập bằng Python thuần đọc thẳng CSV, không dùng SQL.",
        f"- **Kết luận: {'✅ TẤT CẢ PASS' if ok_all else '❌ CÓ MỤC FAIL'}**",
        "",
        "## 1. Số bản ghi sau import",
        "",
        "| Bảng | Đếm lại từ CSV | Trong CSDL | Kết quả |",
        "|---|---:|---:|:---:|",
        *[f"| `{t}` | {fmt(e)} | {fmt(a)} | {'✅ PASS' if ok else '❌ FAIL'} |" for t, e, a, ok in count_rows],
        "",
        f"`PRAGMA integrity_check` = **{integrity}**; lỗi khóa ngoại (`PRAGMA foreign_key_check`) = **{fk_errors}**.",
        "",
        "Quy tắc đếm lại khớp với quy tắc import:",
        "- `products` và `price_snapshots` = dữ liệu gốc cộng các lần thu thập bằng crawler.",
        "- `product_categories` chỉ gồm 6 danh mục hợp lệ, đã bỏ cặp trùng.",
        "- `product_matching` chỉ gồm dòng có `match_id` và sản phẩm tồn tại. 21 dòng `review_only_candidate` không có `match_id` nên không nạp.",
        "- `reviews` đã bỏ dòng trùng (nguồn + sản phẩm + review_id) và rating ngoài khoảng 1–5.",
        "",
        "## 2. Đối chiếu truy vấn với phép tính độc lập",
        "",
        "| Truy vấn | Loại | Số dòng | Kết quả |",
        "|---|---|---:|:---:|",
    ]
    kinds = {"Q1": "find + filter + projection + sort", "Q2": "sort + limit", "Q3": "aggregation ($group)", "Q4": "filter + aggregation",
             "Q5": "aggregation trên lịch sử giá", "Q6": "aggregation trên review", "Q7": "lookup (join) + sort + limit"}
    for name, n, status, _ in query_rows:
        out.append(f"| `{name}` | {kinds.get(name[:2], '')} | {n} | {'✅ PASS' if status == 'PASS' else '❌ FAIL' if status == 'FAIL' else 'ⓘ ' + status} |")
    out += ["", "## 3. Kết quả mẫu (tối đa 5 dòng mỗi truy vấn)", ""]
    for name, _, _, sample in query_rows:
        if not sample:
            continue
        cols = list(sample[0])
        out += [f"### {name}", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        out += ["| " + " | ".join(fmt(r[c]) if not isinstance(r[c], str) else r[c].replace("|", "/")[:70] for c in cols) + " |" for r in sample]
        out.append("")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
