"""Làm sạch, chuẩn hóa dữ liệu thô (dataset/raw) và nạp vào CSDL SQLite (dataset/beautyprice.db).

Chạy:
    python build_database.py            # tạo CSDL nếu chưa có
    python build_database.py --force    # dựng lại từ đầu (CSDL cũ được đổi tên .bak)

Chỉ dùng thư viện chuẩn của Python. Mỗi bước làm sạch ghi số dòng vào bảng etl_log.
"""
import argparse
import csv
import hashlib
import os
import secrets
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = Path(os.environ.get("BEAUTY_RAW_DIR", ROOT / "dataset" / "raw"))
DB_PATH = Path(os.environ.get("BEAUTY_DB", ROOT / "dataset" / "beautyprice.db"))
SCHEMA = Path(__file__).with_name("schema.sql")

VALID_CATEGORIES = ["Kem chống nắng", "Serum", "Sữa rửa mặt", "Sữa tắm", "Tẩy trang", "Tẩy tế bào chết"]
PRODUCT_TYPES = {"single", "bundle", "multi_pack", "unknown"}
ZERO_WIDTH = re.compile(r"[\u200b-\u200d\ufeff]")
RUN_AT = datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- hàm làm sạch

def clean_text(value):
    """Chuẩn Unicode NFC, bỏ ký tự vô hình, gộp khoảng trắng. Chuỗi rỗng -> None."""
    if value is None:
        return None
    text = ZERO_WIDTH.sub("", unicodedata.normalize("NFC", str(value)))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_number(value):
    """'549000', '549.000', '1,234,567', '12,5', '549.000đ' -> float; không hợp lệ -> None."""
    s = (clean_text(value) or "").lower()
    for ch in ("đ", "₫", "vnd", "%", " "):
        s = s.replace(ch, "")
    if s in {"", "nan", "none", "null", "n/a"}:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head}.{tail}" if s.count(",") == 1 and len(tail) <= 2 else s.replace(",", "")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3 and s.split(".")[0].isdigit()):
        s = s.replace(".", "")
    try:
        number = float(s)
    except ValueError:
        return None
    return number if number == number and abs(number) != float("inf") else None


def parse_bool(value):
    s = (clean_text(value) or "").lower()
    if s in {"true", "1", "yes", "y", "có", "co"}:
        return 1
    if s in {"false", "0", "no", "n", "không", "khong"}:
        return 0
    return None


def parse_review_date(value):
    """Hasaki '2025-09-27 17:17:59', Guardian '22 tháng 4, 2025' -> ISO 8601."""
    s = clean_text(value) or ""
    m = re.match(r"^(\d{1,2})\s*th[aá]ng\s*(\d{1,2}),?\s*(\d{4})", s, re.I)
    if m:
        day, month, year = map(int, m.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        date = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        return f"{date}T{int(hh):02d}:{mm}:{ss or '00'}" if hh else date
    return None


def normalize_url(url):
    url = (clean_text(url) or "").lower().split("#")[0].split("?")[0].rstrip("/")
    return re.sub(r"^https?://(www\.)?", "", url)


def product_review_key(retailer_id, url):
    """Khóa nối review: Hasaki dùng số ID cuối URL, Guardian dùng URL đã chuẩn hóa."""
    if retailer_id == "hasaki":
        m = re.search(r"-(\d+)\.html", url or "")
        return f"hasaki:{m.group(1)}" if m else None
    if retailer_id == "guardian" and url:
        return f"guardian:{normalize_url(url)}"
    return None


def extract_attributes(name):
    """Trích dung tích (ml), khối lượng (g), số món trong gói, có phải combo từ tên sản phẩm."""
    low = (name or "").lower().replace(",", ".")
    volume = weight = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|l)\b", low)
    if m:
        volume = float(m.group(1)) * (1000 if m.group(2) == "l" else 1)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(g|gr|gram|kg)\b", low)
    if m:
        weight = float(m.group(1)) * (1000 if m.group(2) == "kg" else 1)
    # "&" / "+" không đủ để kết luận combo (VD "Matcha & Khổ Qua" là tên mùi hương).
    is_combo = int(bool(re.search(r"\bcombo\b|\bbộ\b|\bset\b", low)))
    pack = None
    m = re.search(r"\bcombo\s*(\d{1,2})\b|\bbộ\s*(\d{1,2})\b|\bx\s?(\d{1,2})\b"
                  r"|\b(\d{1,2})\s*(?:chai|tuýp|tuyp|hộp|gói|miếng|lọ|món|cái)\b", low)
    if m:
        pack = int(next(g for g in m.groups() if g))
        if is_combo and pack == 1:  # "Combo 1 A & 1 B" -> không suy ra được tổng số món
            pack = None
    elif not is_combo:
        pack = 1
    return volume if volume and volume > 0 else None, weight if weight and weight > 0 else None, pack if pack and pack > 0 else None, is_combo


def brand_key(brand):
    """Khóa so khớp thương hiệu: bỏ dấu, ký tự đặc biệt, hoa/thường ("L'Oréal" = "L'Oreal", "LA ROCHE POSAY" = "La Roche-Posay")."""
    s = unicodedata.normalize("NFD", (brand or "").casefold()).replace("đ", "d")
    return re.sub(r"[^0-9a-z]", "", "".join(ch for ch in s if not unicodedata.combining(ch)))


def canonical_brands(rows):
    """Gộp các cách viết của cùng thương hiệu về cách viết phổ biến nhất (hòa thì ưu tiên không viết hoa toàn bộ)."""
    variants = defaultdict(Counter)
    for row in rows:
        brand = clean_text(row.get("brand")) or clean_text(row.get("brand_original"))
        if brand:
            variants[brand_key(brand)][brand] += 1
    return {key: max(counter.items(), key=lambda kv: (kv[1], not kv[0].isupper()))[0] for key, counter in variants.items()}


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        return [{(k or "").strip(): v for k, v in row.items() if k} for row in csv.DictReader(file)]


def find_raw(pattern):
    matches = sorted(RAW_DIR.rglob(pattern))
    if not matches:
        sys.exit(f"Không tìm thấy file {pattern} trong {RAW_DIR}")
    return matches[0]


# ---------------------------------------------------------------- nạp từng bảng

class Loader:
    def __init__(self, conn):
        self.conn = conn

    def log(self, step, table, rows_in, rows_out, affected=0, note=""):
        self.conn.execute(
            "INSERT INTO etl_log(run_at, step, table_name, rows_in, rows_out, rows_affected, note) VALUES (?,?,?,?,?,?,?)",
            (RUN_AT, step, table, rows_in, rows_out, affected, note))
        print(f"  - {step:<48} {table:<18} vào={rows_in:<6} ra={rows_out:<6} tác động={affected:<5} {note}")

    def retailers(self):
        rows = read_csv(find_raw("retailers.csv"))
        data = [(clean_text(r["retailer_id"]).lower(), clean_text(r["retailer_name"]), clean_text(r.get("country")),
                 clean_text(r.get("currency")) or "VND", clean_text(r.get("website_url")),
                 1 if parse_bool(r.get("is_active")) != 0 else 0) for r in rows]
        self.conn.executemany("INSERT INTO retailers VALUES (?,?,?,?,?,?)", data)
        self.log("Nạp nhà bán lẻ", "retailers", len(rows), len(data))
        return {d[0] for d in data}

    def categories(self):
        self.conn.executemany("INSERT INTO categories(category_name) VALUES (?)", [(c,) for c in VALID_CATEGORIES])
        return dict(self.conn.execute("SELECT category_name, category_id FROM categories"))

    def products(self, retailers, category_ids):
        rows = read_csv(find_raw("products*.csv"))
        brands = canonical_brands(rows)
        seen, data = set(), []
        stats = Counter()
        for r in rows:
            pid, retailer = clean_text(r.get("product_id")), (clean_text(r.get("retailer_id")) or "").lower()
            name = clean_text(r.get("product_name"))
            if not pid or pid in seen:
                stats["duplicate_or_missing_id"] += 1
                continue
            if retailer not in retailers:
                stats["unknown_retailer"] += 1
                continue
            if not name:
                stats["missing_name"] += 1
                continue
            raw_brand = clean_text(r.get("brand")) or clean_text(r.get("brand_original")) or "Không rõ"
            brand = brands.get(brand_key(raw_brand), raw_brand)
            stats["brand_normalized"] += brand != (clean_text(r.get("brand_original")) or brand)
            if name != (r.get("product_name") or "").strip():
                stats["name_cleaned"] += 1
            category = clean_text(r.get("primary_category"))
            if category not in category_ids:
                stats["category_unknown"] += 1
                category = None
            ptype = (clean_text(r.get("product_type")) or "unknown").lower()
            ptype = ptype if ptype in PRODUCT_TYPES else "unknown"
            url = clean_text(r.get("product_url"))
            if url and not url.lower().startswith("http"):
                stats["invalid_url"] += 1
                url = None
            volume, weight, pack, is_combo = extract_attributes(name)
            if ptype == "bundle":
                is_combo = 1
            seen.add(pid)
            data.append((pid, retailer, name, brand, category_ids.get(category), ptype, url,
                         product_review_key(retailer, url), volume, weight, pack, is_combo))
        self.conn.executemany(
            """INSERT INTO products(product_id, retailer_id, product_name, brand, category_id, product_type, product_url,
                                    review_key, volume_ml, weight_g, pack_count, is_combo)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", data)
        self.log("Loại trùng/thiếu khóa sản phẩm", "products", len(rows), len(data), stats["duplicate_or_missing_id"])
        self.log("Chuẩn hóa tên thương hiệu (gộp hoa/thường, dấu, ký tự đặc biệt)", "products", len(data), len(data), stats["brand_normalized"],
                 f"{len(set(d[3] for d in data))} thương hiệu")
        self.log("Làm sạch tên (Unicode, khoảng trắng, ký tự vô hình)", "products", len(data), len(data), stats["name_cleaned"])
        self.log("Danh mục chính không hợp lệ/trống -> NULL", "products", len(data), len(data), stats["category_unknown"])
        self.log("Trích thuộc tính từ tên (ml, g, số món, combo)", "products", len(data), len(data),
                 sum(1 for d in data if d[8] or d[9]), "có dung tích hoặc khối lượng")
        self.log("Tạo khóa nối review theo ID nguồn", "products", len(data), len(data), sum(1 for d in data if d[7]))
        return {d[0] for d in data}

    def product_categories(self, product_ids, category_ids):
        rows = read_csv(find_raw("product_categories (*).csv"))
        pairs = set()
        for r in rows:
            pid, cat = clean_text(r.get("product_id")), clean_text(r.get("category"))
            if pid in product_ids and cat in category_ids:
                pairs.add((pid, category_ids[cat]))
        self.conn.executemany("INSERT INTO product_categories VALUES (?,?)", sorted(pairs))
        self.log("Loại cặp sản phẩm-danh mục trùng/không hợp lệ", "product_categories", len(rows), len(pairs), len(rows) - len(pairs))
        # Sản phẩm thiếu danh mục chính nhưng chỉ có đúng 1 nhãn -> gán làm danh mục chính.
        filled = self.conn.execute("""
            UPDATE products SET category_id = (SELECT MIN(category_id) FROM product_categories pc WHERE pc.product_id = products.product_id)
            WHERE category_id IS NULL
              AND (SELECT COUNT(*) FROM product_categories pc WHERE pc.product_id = products.product_id) = 1""").rowcount
        self.log("Bổ sung danh mục chính từ nhãn duy nhất", "products", len(product_ids), len(product_ids), filled)

    def snapshots(self, product_ids):
        rows = read_csv(find_raw("price_snapshots*.csv"))
        seen, keys, data = set(), set(), []
        stats = Counter()
        for r in rows:
            sid, pid = clean_text(r.get("snapshot_id")), clean_text(r.get("product_id"))
            if not sid or sid in seen or pid not in product_ids:
                stats["bad_key"] += 1
                continue
            price, listed = parse_number(r.get("current_price_vnd")), parse_number(r.get("listed_price_vnd"))
            if not price or price <= 0:
                stats["invalid_price"] += 1
                continue
            collected = clean_text(r.get("collected_at"))
            dedupe_key = (pid, collected, price, listed)
            if dedupe_key in keys:
                stats["duplicate_snapshot"] += 1
                continue
            if listed is not None and listed <= 0:
                listed = None
            if listed is not None and listed < price:
                stats["listed_below_current"] += 1
                listed = None
            source_discount = parse_number(r.get("discount_percent_source") or r.get("discount_percent"))
            if listed:
                discount = round((listed - price) / listed * 100, 2)
                if source_discount is not None and abs(source_discount - discount) > 1:
                    stats["discount_mismatch_fixed"] += 1
            else:
                discount = None
                stats["discount_missing"] += 1
            rating = parse_number(r.get("rating"))
            if rating is not None and not 0 < rating <= 5:
                stats["rating_zero_or_invalid"] += 1
                rating = None
            reviews = parse_number(r.get("review_count"))
            reviews = int(reviews) if reviews is not None and reviews >= 0 else None
            seen.add(sid)
            keys.add(dedupe_key)
            data.append((sid, pid, price, listed, discount, source_discount, rating, reviews, collected, clean_text(r.get("source_file"))))
        self.conn.executemany(
            """INSERT INTO price_snapshots(snapshot_id, product_id, current_price_vnd, listed_price_vnd, discount_percent,
                                           discount_source, rating, review_count, collected_at, source_file)
               VALUES (?,?,?,?,?,?,?,?,?,?)""", data)
        n = len(data)
        self.log("Loại snapshot sai khóa/không khớp sản phẩm", "price_snapshots", len(rows), n, stats["bad_key"])
        self.log("Loại giá không hợp lệ (<= 0 hoặc không đọc được)", "price_snapshots", len(rows), n, stats["invalid_price"])
        self.log("Loại snapshot trùng (cùng sản phẩm, thời điểm, giá)", "price_snapshots", len(rows), n, stats["duplicate_snapshot"])
        self.log("Giá niêm yết < giá bán -> bỏ giá niêm yết", "price_snapshots", n, n, stats["listed_below_current"])
        self.log("Tính lại % giảm = (niêm yết - bán)/niêm yết", "price_snapshots", n, n, n - stats["discount_missing"],
                 f"{stats['discount_mismatch_fixed']} dòng lệch nguồn > 1 điểm %")
        self.log("Không đủ cặp giá -> % giảm để NULL (không đoán)", "price_snapshots", n, n, stats["discount_missing"])
        self.log("Rating = 0 hoặc ngoài 0-5 -> NULL (chưa có đánh giá)", "price_snapshots", n, n, stats["rating_zero_or_invalid"])

    def reviews(self, retailers):
        product_by_key = dict(self.conn.execute("SELECT review_key, product_id FROM products WHERE review_key IS NOT NULL"))
        total_in, data, seen = 0, [], set()
        stats = Counter()
        for path in sorted(RAW_DIR.rglob("*_reviews.csv")):
            default_source = path.name.split("_")[0].lower()
            rows = read_csv(path)
            total_in += len(rows)
            for r in rows:
                source = (clean_text(r.get("source")) or default_source).lower()
                source = source if source in retailers else default_source
                spid, rid = clean_text(r.get("source_product_id")), clean_text(r.get("review_id"))
                rating = parse_number(r.get("rating"))
                if not spid or not rid:
                    stats["missing_key"] += 1
                    continue
                if rating is None or not 1 <= rating <= 5:
                    stats["invalid_rating"] += 1
                    continue
                if parse_bool(r.get("is_duplicate")) == 1 or (source, spid, rid) in seen:
                    stats["duplicate"] += 1
                    continue
                raw_date = clean_text(r.get("review_date"))
                review_date = parse_review_date(raw_date)
                stats["date_unparsed"] += raw_date is not None and review_date is None
                key = f"hasaki:{spid}" if source == "hasaki" else (f"{source}:{normalize_url(r.get('source_url'))}" if r.get("source_url") else None)
                product_id = product_by_key.get(key)
                stats["linked"] += product_id is not None
                seen.add((source, spid, rid))
                data.append((source, spid, rid, product_id, key, clean_text(r.get("product_name")), clean_text(r.get("category")),
                             round(rating, 1), clean_text(r.get("review_text") or r.get("content_clean")), review_date, raw_date,
                             parse_bool(r.get("is_bought")), parse_bool(r.get("has_images")), clean_text(r.get("source_url"))))
        self.conn.executemany(
            """INSERT INTO reviews(source, source_product_id, review_id, product_id, review_key, product_name, category, rating,
                                   review_text, review_date, review_date_raw, is_bought, has_images, source_url)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", data)
        n = len(data)
        self.log("Loại review thiếu khóa", "reviews", total_in, n, stats["missing_key"])
        self.log("Loại review rating ngoài 1-5 (giữ nửa sao)", "reviews", total_in, n, stats["invalid_rating"])
        self.log("Loại review trùng (nguồn + sản phẩm + review_id)", "reviews", total_in, n, stats["duplicate"])
        self.log("Chuẩn hóa ngày review về ISO 8601", "reviews", n, n, n - stats["date_unparsed"], f"{stats['date_unparsed']} không đọc được")
        self.log("Nối review với sản phẩm theo ID nguồn", "reviews", n, n, stats["linked"])

    def collection_logs(self, retailers):
        rows = read_csv(find_raw("collection_logs.csv"))
        data = []
        for r in rows:
            retailer = (clean_text(r.get("retailer_id")) or "").lower()
            to_int = lambda v: int(parse_number(v)) if parse_number(v) is not None else None
            data.append((clean_text(r.get("run_id")), retailer if retailer in retailers else None, clean_text(r.get("script_name")),
                         clean_text(r.get("started_at")), clean_text(r.get("finished_at")), to_int(r.get("pages_attempted")),
                         to_int(r.get("records_found")), to_int(r.get("records_saved")), to_int(r.get("records_failed")),
                         clean_text(r.get("status")), clean_text(r.get("error_message")), clean_text(r.get("run_type"))))
        self.conn.executemany("INSERT OR IGNORE INTO collection_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", data)
        self.log("Nạp nhật ký thu thập", "collection_logs", len(rows), len(data))

    def matching(self, product_ids):
        rows = read_csv(find_raw("product_matching.csv"))
        data = [(clean_text(r["match_id"]), clean_text(r.get("match_group_id")), clean_text(r.get("product_id")),
                 clean_text(r.get("retailer_id")), clean_text(r.get("match_method")), parse_number(r.get("match_confidence")),
                 clean_text(r.get("match_status")), parse_bool(r.get("verified_by_human")) or 0)
                for r in rows if clean_text(r.get("match_id")) and clean_text(r.get("product_id")) in product_ids]
        self.conn.executemany("INSERT OR IGNORE INTO product_matching VALUES (?,?,?,?,?,?,?,?)", data)
        self.log("Nạp ứng viên đối chiếu sản phẩm", "product_matching", len(rows), len(data))


def import_crawl_runs(conn):
    """Nạp lại các lần thu thập bằng crawler (dataset/crawl/crawl_*/) - chỉ khi chạy với --with-crawl.
    Mặc định CSDL chỉ gồm dữ liệu gốc dataset/raw (5.657 sản phẩm), khớp EDA/KPI."""
    crawl_dir = ROOT / "dataset" / "crawl"
    runs = sorted(p for p in crawl_dir.glob("crawl_*") if (p / "snapshots.csv").exists()) if crawl_dir.exists() else []
    if not runs:
        return
    sys.path.insert(0, str(ROOT / "source-code" / "crawler"))
    import crawl
    for run in runs:
        records, logs, run_id, _, reviews = crawl.load_run(run)
        records, _ = crawl.clean_records(records)  # áp quy tắc làm sạch hiện hành cho dữ liệu đã lưu
        new_products, new_snapshots = crawl.import_records(conn, records, logs, run_id, RUN_AT, allow_new_products=True)
        added, named = crawl.import_reviews(conn, crawl.clean_reviews(reviews), run_id, RUN_AT, allow_new_reviews=True) if reviews else (0, 0)
        print(f"  - Nạp lần thu thập {run_id:<36} +{new_snapshots} snapshot, +{new_products} sản phẩm mới"
              + (f", +{added} review, bổ sung tên {named} review" if reviews else ""))


def password_hash(password, iterations=600000):
    """Băm PBKDF2-SHA256 cùng định dạng với werkzeug (backend kiểm tra bằng check_password_hash)."""
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2:sha256:{iterations}${salt}${digest}"


def seed_users(conn):
    """Tạo sẵn tài khoản demo để lần chạy đầu website không phải ghi vào CSDL."""
    conn.executemany("INSERT OR IGNORE INTO users(username, password_hash, role) VALUES (?,?,?)", [
        ("admin", password_hash(os.environ.get("BEAUTY_ADMIN_PASSWORD", "Admin@123")), "Admin"),
        ("user", password_hash(os.environ.get("BEAUTY_USER_PASSWORD", "User@123")), "User"),
    ])


def build(db_path, with_crawl=False):
    tmp = db_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    loader = Loader(conn)
    print(f"Nguồn dữ liệu thô: {RAW_DIR}")
    retailers = loader.retailers()
    category_ids = loader.categories()
    product_ids = loader.products(retailers, category_ids)
    loader.product_categories(product_ids, category_ids)
    loader.snapshots(product_ids)
    orphan = conn.execute("SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM price_snapshots s WHERE s.product_id = p.product_id)").fetchone()[0]
    if orphan:
        conn.execute("DELETE FROM products WHERE product_id NOT IN (SELECT product_id FROM price_snapshots)")
    loader.log("Loại sản phẩm không có giá hợp lệ", "products", len(product_ids), len(product_ids) - orphan, orphan)
    loader.reviews(retailers)
    loader.collection_logs(retailers)
    loader.matching(product_ids)
    if with_crawl:
        import_crawl_runs(conn)
    seed_users(conn)
    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        sys.exit(f"Lỗi khóa ngoại: {problems[:5]}")
    conn.commit()
    conn.close()
    os.replace(tmp, db_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="dựng lại CSDL (bản cũ đổi tên thành .bak)")
    parser.add_argument("--with-crawl", action="store_true",
                        help="nạp thêm các lần thu thập trong dataset/crawl (mặc định chỉ dữ liệu gốc dataset/raw)")
    args = parser.parse_args()
    if DB_PATH.exists() and not args.force:
        print(f"CSDL đã tồn tại: {DB_PATH} (dùng --force để dựng lại)")
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        backup = DB_PATH.with_suffix(f".{datetime.now():%Y%m%d%H%M%S}.bak")
        os.replace(DB_PATH, backup)
        print(f"Đã sao lưu CSDL cũ: {backup.name}")
    print("Đang làm sạch và nạp dữ liệu...")
    build(DB_PATH, args.with_crawl)
    conn = sqlite3.connect(DB_PATH)
    for table in ("retailers", "categories", "products", "product_categories", "price_snapshots", "reviews",
                  "collection_logs", "product_matching"):
        print(f"  {table:<20} {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:>6} dòng")
    conn.close()
    print(f"Xong: {DB_PATH}")
    print("Bước tiếp theo (tùy chọn): python train_models.py  -> huấn luyện mô hình và ghi kết quả vào CSDL")


if __name__ == "__main__":
    main()
