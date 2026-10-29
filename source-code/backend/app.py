"""BeautyPrice Intelligence - Flask backend trên CSDL SQLite.

Chạy: python app.py  rồi mở http://127.0.0.1:5000/
- CSDL: dataset/beautyprice.db (tự dựng từ dataset/raw nếu chưa có).
- Backend phục vụ luôn thư mục source-code/frontend nên không cần Live Server.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import statistics
import sys
import threading
import time
import unicodedata
import uuid
from collections import Counter
from contextlib import closing
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, g, jsonify, redirect, request, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "source-code" / "frontend"
PIPELINE_DIR = ROOT / "source-code" / "pipeline"
DB_PATH = Path(os.environ.get("BEAUTY_DB", ROOT / "dataset" / "beautyprice.db"))
BACKUP_DIR = Path(os.environ.get("BEAUTY_BACKUP_DIR", DB_PATH.parent / "backups"))

SESSION_TTL = int(os.environ.get("BEAUTY_SESSION_TTL", 8 * 3600))
MAX_LOGIN_FAILS, LOGIN_LOCK_SECONDS = 5, 300
STATIC_EXTENSIONS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp", ".woff", ".woff2"}
SEGMENTS = ["Thấp", "Trung bình", "Cao"]

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
CORS(app, resources={r"/api/*": {
    "origins": os.environ.get("BEAUTY_CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(","),
    "allow_headers": ["Content-Type", "Authorization"],
}})

PERMISSIONS = {
    "Admin": dict.fromkeys(["view", "create", "update", "delete", "export", "backup", "restore"], True),
    "User": {"view": True, "export": True, **dict.fromkeys(["create", "update", "delete", "backup", "restore"], False)},
}
SESSIONS, LOGIN_FAILS = {}, {}
AUTH_LOCK = threading.Lock()


# ---------------------------------------------------------------- CSDL

def ensure_database():
    """Dựng CSDL từ dataset/raw nếu chưa có; tạo tài khoản mặc định nếu bảng users trống."""
    if not DB_PATH.exists():
        print("Chưa có CSDL -> đang dựng từ dataset/raw ...")
        sys.path.insert(0, str(PIPELINE_DIR))
        import build_database
        build_database.DB_PATH = DB_PATH
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        build_database.build(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        if not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            conn.executemany("INSERT INTO users(username, password_hash, role) VALUES (?,?,?)", [
                ("admin", generate_password_hash(os.environ.get("BEAUTY_ADMIN_PASSWORD", "Admin@123"), method="pbkdf2:sha256"), "Admin"),
                ("user", generate_password_hash(os.environ.get("BEAUTY_USER_PASSWORD", "User@123"), method="pbkdf2:sha256"), "User"),
            ])


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def rows(sql, params=()):
    return [dict(r) for r in db().execute(sql, params).fetchall()]


def one(sql, params=()):
    row = db().execute(sql, params).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------- helpers

def text(value):
    return str(value if value is not None else "").strip()


def number(value):
    """Số hữu hạn hoặc None. Nhận '549000', '549.000', '549,000', '12,5'."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value and abs(value) != float("inf") else None
    s = text(value).lower().replace("đ", "").replace("₫", "").replace(" ", "").replace("%", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head}.{tail}" if s.count(",") == 1 and len(tail) <= 2 else s.replace(",", "")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3 and s.split(".")[0].isdigit()):
        s = s.replace(".", "")
    try:
        result = float(s)
    except ValueError:
        return None
    return result if result == result and abs(result) != float("inf") else None


def brand_key(brand):
    s = unicodedata.normalize("NFD", text(brand).casefold()).replace("đ", "d")
    return re.sub(r"[^0-9a-z]", "", "".join(ch for ch in s if not unicodedata.combining(ch)))


def ok(**payload):
    return jsonify({"status": "success", **payload})


def fail(message, http_status=400, **extra):
    return jsonify({"status": "error", "message": message, **extra}), http_status


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def latest_run(task, selected_only=True):
    row = one(f"SELECT * FROM ml_runs WHERE task = ? {'AND is_selected = 1' if selected_only else ''} ORDER BY run_id DESC LIMIT 1", (task,))
    if row:
        row["params"], row["metrics"] = json.loads(row.pop("params_json") or "{}"), json.loads(row.pop("metrics_json") or "{}")
    return row


def all_runs(task):
    result = rows("SELECT model_name, is_selected, metrics_json FROM ml_runs WHERE task = ? ORDER BY run_id", (task,))
    for r in result:
        r["metrics"] = json.loads(r.pop("metrics_json") or "{}")
        r["is_selected"] = bool(r["is_selected"])
    return result


# ---------------------------------------------------------------- auth

def current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    with AUTH_LOCK:
        token = header[7:].strip()
        session = SESSIONS.get(token)
        if session and session["expires_at"] < time.time():
            SESSIONS.pop(token, None)
            session = None
    return session


def require_auth(roles=None):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return fail("Bạn chưa đăng nhập hoặc phiên đăng nhập đã hết hạn!", 401, code="AUTH_REQUIRED")
            if roles and user["role"] not in roles:
                return fail("Bạn không có quyền thực hiện chức năng này!", 403, code="FORBIDDEN")
            g.current_user = user
            return function(*args, **kwargs)
        return wrapper
    return decorator


@app.post("/api/login")
def login():
    data = json_body()
    username, password = text(data.get("username")), str(data.get("password") or "")
    if not username or not password:
        return fail("Vui lòng nhập tài khoản và mật khẩu!")
    client, now = request.remote_addr or "?", time.time()
    with AUTH_LOCK:
        fails, since = LOGIN_FAILS.get(client, (0, now))
        if fails >= MAX_LOGIN_FAILS and now - since < LOGIN_LOCK_SECONDS:
            return fail("Đăng nhập sai quá nhiều lần, vui lòng thử lại sau ít phút!", 429)

    user = one("SELECT username, password_hash, role FROM users WHERE username = ?", (username,))
    if user is None or not check_password_hash(user["password_hash"], password):
        with AUTH_LOCK:
            fails, since = LOGIN_FAILS.get(client, (0, now))
            LOGIN_FAILS[client] = (1, now) if now - since >= LOGIN_LOCK_SECONDS else (fails + 1, since)
        return fail("Tài khoản hoặc mật khẩu không đúng!", 401)

    token = secrets.token_urlsafe(32)
    with AUTH_LOCK:
        LOGIN_FAILS.pop(client, None)
        for key in [k for k, s in SESSIONS.items() if s["expires_at"] < now]:
            SESSIONS.pop(key)
        SESSIONS[token] = {"username": username, "role": user["role"],
                           "login_at": datetime.now().isoformat(timespec="seconds"), "expires_at": now + SESSION_TTL}
    return ok(message="Đăng nhập thành công!", token=token, expires_in=SESSION_TTL,
              user={"username": username, "role": user["role"]}, permissions=PERMISSIONS[user["role"]])


@app.get("/api/me")
@require_auth()
def me():
    user = g.current_user
    return ok(user={k: user[k] for k in ("username", "role", "login_at")}, permissions=PERMISSIONS[user["role"]])


@app.post("/api/logout")
@require_auth()
def logout():
    with AUTH_LOCK:
        SESSIONS.pop(request.headers["Authorization"][7:].strip(), None)
    return ok(message="Đăng xuất thành công!")


@app.get("/api/permissions")
@require_auth()
def permissions():
    return ok(permissions=PERMISSIONS)


@app.get("/api/test")
def test_api():
    return ok(message="API hoạt động bình thường!", database=DB_PATH.name)


# ---------------------------------------------------------------- sản phẩm

PRODUCT_SQL = """
    SELECT v.product_id AS id, v.product_id, v.retailer_id, v.source, v.product_name, v.brand, v.category,
           v.product_type, v.product_url, v.review_key, v.current_price_vnd, v.listed_price_vnd, v.discount_percent,
           v.rating, v.review_count, v.collected_at, v.data_origin, v.volume_ml, v.weight_g, v.pack_count, v.is_combo,
           (SELECT COUNT(*) FROM price_snapshots s WHERE s.product_id = v.product_id) AS snapshot_count
    FROM v_products v
"""


def product_row(product_id):
    return one(PRODUCT_SQL + " WHERE v.product_id = ?", (product_id,))


@app.get("/api/products")
@require_auth()
def get_products():
    products = rows(PRODUCT_SQL + " ORDER BY v.product_name COLLATE NOCASE")
    return ok(total=len(products), products=products)


@app.get("/api/products/<product_id>")
@require_auth()
def get_product(product_id):
    product = product_row(product_id)
    if product is None:
        return fail("Không tìm thấy sản phẩm!", 404)
    history = rows("""SELECT snapshot_id, current_price_vnd, listed_price_vnd, discount_percent, rating, review_count,
                             collected_at, data_origin FROM price_snapshots WHERE product_id = ? ORDER BY collected_at""", (product_id,))
    categories = [r["category_name"] for r in rows("""SELECT c.category_name FROM product_categories pc
                    JOIN categories c ON c.category_id = pc.category_id WHERE pc.product_id = ?""", (product_id,))]
    return ok(product=product, history=history, categories=categories)


@app.get("/api/products/<product_id>/history")
@require_auth()
def get_product_history(product_id):
    history = rows("SELECT * FROM price_snapshots WHERE product_id = ? ORDER BY collected_at", (product_id,))
    return ok(total=len(history), history=history)


@app.get("/api/lookups")
@require_auth()
def lookups():
    return ok(retailers=rows("SELECT retailer_id, retailer_name FROM retailers ORDER BY retailer_name"),
              categories=[r["category_name"] for r in rows("SELECT category_name FROM categories ORDER BY category_name")])


def validate_product(data, current=None):
    """Kiểm tra dữ liệu gửi lên. Trả về (thông tin sản phẩm, giá mới hoặc None, lỗi)."""
    merged = {**(current or {}), **{k: v for k, v in data.items() if v is not None}}
    name, brand = text(merged.get("product_name")), text(merged.get("brand"))
    if not name or len(name) > 300:
        return None, None, "Tên sản phẩm không được để trống và tối đa 300 ký tự!"
    if not brand or len(brand) > 120:
        return None, None, "Thương hiệu không được để trống và tối đa 120 ký tự!"
    # Thương hiệu đã có (khác hoa/thường, dấu, ký tự đặc biệt) -> dùng đúng cách viết trong CSDL.
    key = brand_key(brand)
    brand = next((b["brand"] for b in rows("SELECT DISTINCT brand FROM products") if brand_key(b["brand"]) == key), brand)
    retailer = text(merged.get("retailer_id")).lower()
    if not one("SELECT 1 FROM retailers WHERE retailer_id = ?", (retailer,)):
        return None, None, "Nhà bán lẻ không hợp lệ!"
    category = text(merged.get("category")) or None
    category_id = None
    if category:
        found = one("SELECT category_id FROM categories WHERE category_name = ?", (category,))
        if not found:
            return None, None, "Danh mục không hợp lệ!"
        category_id = found["category_id"]
    url = text(merged.get("product_url")) or None
    if url and urlparse(url).scheme not in ("http", "https"):
        return None, None, "Link sản phẩm phải bắt đầu bằng http:// hoặc https://"

    info = {"product_name": name, "brand": brand, "retailer_id": retailer, "category_id": category_id, "product_url": url}
    price_fields = ("current_price_vnd", "listed_price_vnd")
    if current is not None and not any(f in data for f in price_fields):
        return info, None, None
    price, listed = number(merged.get("current_price_vnd")), number(merged.get("listed_price_vnd"))
    if not price or price <= 0:
        return None, None, "Giá hiện tại phải lớn hơn 0!"
    if listed is not None and listed <= 0:
        listed = None
    if listed is not None and listed < price:
        return None, None, "Giá niêm yết phải lớn hơn hoặc bằng giá hiện tại!"
    discount = round((listed - price) / listed * 100, 2) if listed else None
    return info, {"current_price_vnd": price, "listed_price_vnd": listed, "discount_percent": discount}, None


def insert_snapshot(conn, product_id, price, previous=None):
    conn.execute("""INSERT INTO price_snapshots(snapshot_id, product_id, current_price_vnd, listed_price_vnd, discount_percent,
                                                rating, review_count, collected_at, data_origin)
                    VALUES (?,?,?,?,?,?,?,?, 'manual')""",
                 (f"snap_{uuid.uuid4().hex[:16]}", product_id, price["current_price_vnd"], price["listed_price_vnd"],
                  price["discount_percent"], (previous or {}).get("rating"), (previous or {}).get("review_count"),
                  datetime.now().astimezone().isoformat(timespec="seconds")))


@app.post("/api/products")
@require_auth(["Admin"])
def create_product():
    info, price, error = validate_product(json_body())
    if error:
        return fail(error)
    product_id = f"prod_{uuid.uuid4().hex[:16]}"
    conn = db()
    with conn:
        conn.execute("""INSERT INTO products(product_id, retailer_id, product_name, brand, category_id, product_url, data_origin)
                        VALUES (?,?,?,?,?,?, 'manual')""",
                     (product_id, info["retailer_id"], info["product_name"], info["brand"], info["category_id"], info["product_url"]))
        if info["category_id"]:
            conn.execute("INSERT INTO product_categories VALUES (?,?)", (product_id, info["category_id"]))
        insert_snapshot(conn, product_id, price)
    return ok(message="Thêm sản phẩm thành công!", product=product_row(product_id)), 201


@app.put("/api/products/<product_id>")
@require_auth(["Admin"])
def update_product(product_id):
    current = product_row(product_id)
    if current is None:
        return fail("Không tìm thấy sản phẩm!", 404)
    data = {k: v for k, v in json_body().items() if k not in ("id", "product_id")}
    if "source" in data and "retailer_id" not in data:  # tương thích form cũ gửi tên nhà bán lẻ
        found = one("SELECT retailer_id FROM retailers WHERE retailer_name = ? OR retailer_id = ?", (data["source"], text(data["source"]).lower()))
        if found:
            data["retailer_id"] = found["retailer_id"]
    info, price, error = validate_product(data, current)
    if error:
        return fail(error)
    old_category_id = one("SELECT category_id FROM products WHERE product_id = ?", (product_id,))["category_id"]
    conn = db()
    with conn:
        conn.execute("""UPDATE products SET product_name = ?, brand = ?, retailer_id = ?, category_id = ?, product_url = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') WHERE product_id = ?""",
                     (info["product_name"], info["brand"], info["retailer_id"], info["category_id"], info["product_url"], product_id))
        if old_category_id != info["category_id"]:
            # Đổi danh mục chính: bỏ nhãn danh mục chính cũ, thêm nhãn mới.
            conn.execute("DELETE FROM product_categories WHERE product_id = ? AND category_id = ?", (product_id, old_category_id))
        if info["category_id"]:
            conn.execute("INSERT OR IGNORE INTO product_categories VALUES (?,?)", (product_id, info["category_id"]))
        # Giá đổi -> thêm snapshot mới để giữ lịch sử biến động giá.
        if price and any(price[k] != current.get(k) for k in ("current_price_vnd", "listed_price_vnd")):
            insert_snapshot(conn, product_id, price, current)
    return ok(message="Cập nhật sản phẩm thành công!", product=product_row(product_id))


@app.delete("/api/products/<product_id>")
@require_auth(["Admin"])
def delete_product(product_id):
    conn = db()
    with conn:
        deleted = conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,)).rowcount
    if not deleted:
        return fail("Không tìm thấy sản phẩm!", 404)
    return ok(message="Xóa sản phẩm thành công!", total=one("SELECT COUNT(*) AS n FROM products")["n"])


@app.get("/api/price-statistics")
@require_auth()
def price_statistics():
    prices = [r["current_price_vnd"] for r in rows("SELECT current_price_vnd FROM v_products WHERE current_price_vnd > 0")]
    if not prices:
        return fail("Không có giá hợp lệ.", 404)
    stats = {"count": len(prices), "mean": mean(prices), "median": median(prices), "min": min(prices), "max": max(prices)}
    return ok(statistics=stats, scope="current_products")


@app.get("/api/price-trend")
@require_auth()
def price_trend():
    """Giá trung vị theo ngày thu thập và nhà bán lẻ (từ toàn bộ lịch sử snapshot)."""
    data = rows("""SELECT substr(s.collected_at, 1, 10) AS day, r.retailer_name AS retailer, s.current_price_vnd AS price
                   FROM price_snapshots s JOIN products p ON p.product_id = s.product_id
                   JOIN retailers r ON r.retailer_id = p.retailer_id""")
    groups = {}
    for r in data:
        groups.setdefault((r["day"], r["retailer"]), []).append(r["price"])
    trend = [{"day": d, "retailer": rt, "median_price": median(v), "snapshots": len(v)} for (d, rt), v in sorted(groups.items())]
    changed = rows("""SELECT p.product_id, p.product_name, r.retailer_name AS retailer, COUNT(*) AS snapshots,
                             MIN(s.current_price_vnd) AS min_price, MAX(s.current_price_vnd) AS max_price
                      FROM price_snapshots s JOIN products p ON p.product_id = s.product_id
                      JOIN retailers r ON r.retailer_id = p.retailer_id
                      GROUP BY p.product_id HAVING MAX(s.current_price_vnd) > MIN(s.current_price_vnd)
                      ORDER BY (MAX(s.current_price_vnd) - MIN(s.current_price_vnd)) * 1.0 / MIN(s.current_price_vnd) DESC LIMIT 20""")
    return ok(trend=trend, top_changes=changed)


@app.get("/api/reviews")
@require_auth()
def get_reviews():
    reviews = rows("""SELECT review_key, product_id, source, source_product_id, review_id, product_name, category, rating,
                             review_text, review_date, review_date_raw, is_bought, has_images, source_url FROM reviews""")
    for r in reviews:
        r["is_bought"] = None if r["is_bought"] is None else bool(r["is_bought"])
        r["has_images"] = None if r["has_images"] is None else bool(r["has_images"])
    return ok(total=len(reviews), reviews=reviews)


@app.get("/api/data-quality")
@require_auth()
def data_quality():
    # Lần dựng CSDL gần nhất + các lần crawler nạp thêm sau đó.
    last = one("SELECT MAX(run_at) AS run_at FROM etl_log WHERE step NOT LIKE 'Nạp lần thu thập%'")["run_at"]
    tables = ["retailers", "categories", "products", "product_categories", "price_snapshots", "reviews", "collection_logs", "product_matching"]
    return ok(run_at=last, steps=rows("SELECT step, table_name, rows_in, rows_out, rows_affected, note FROM etl_log WHERE run_at >= ? ORDER BY id", (last,)),
              tables={t: one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in tables},
              collection=rows("""SELECT r.retailer_name AS retailer, COUNT(*) AS runs, SUM(c.status = 'success') AS success
                                 FROM collection_logs c LEFT JOIN retailers r ON r.retailer_id = c.retailer_id GROUP BY c.retailer_id"""))


# ---------------------------------------------------------------- sao lưu & phục hồi

BACKUP_NAME = re.compile(r"^beautyprice_\d{8}T\d{6}(_[a-z-]+)?\.db$")
CHECK_TABLES = ["retailers", "categories", "products", "product_categories", "price_snapshots", "reviews", "users",
                "collection_logs", "etl_log", "ml_runs", "ml_price_predictions", "ml_clusters", "ml_anomalies"]
BACKUP_LOCK = threading.Lock()


def inspect_db(path):
    """Kiểm tra toàn vẹn + đếm số dòng từng bảng của một file CSDL (mở chỉ đọc)."""
    with closing(sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk_errors = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in CHECK_TABLES}
    return {"integrity": integrity, "foreign_key_errors": fk_errors, "counts": counts}


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(note="", tag=""):
    """Sao lưu bằng SQLite Online Backup API (an toàn khi CSDL đang được dùng), rồi kiểm tra ngay bản sao."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = f"beautyprice_{datetime.now():%Y%m%dT%H%M%S}{'_' + tag if tag else ''}.db"
    path = BACKUP_DIR / name
    with closing(sqlite3.connect(DB_PATH)) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
    info = inspect_db(path)
    meta = {"name": name, "created_at": datetime.now().isoformat(timespec="seconds"), "created_by": g.current_user["username"],
            "note": text(note)[:200], "size_bytes": path.stat().st_size, "sha256": sha256_of(path), **info}
    path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if info["integrity"] != "ok":
        raise RuntimeError(f"Bản sao lưu lỗi toàn vẹn: {info['integrity']}")
    return meta


def backup_meta(path):
    meta_path = path.with_suffix(".json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"name": path.name}
    meta.setdefault("size_bytes", path.stat().st_size)
    return meta


@app.get("/api/backups")
@require_auth(["Admin"])
def list_backups():
    backups = [backup_meta(p) for p in sorted(BACKUP_DIR.glob("beautyprice_*.db"), reverse=True)] if BACKUP_DIR.exists() else []
    return ok(backups=backups, current={"path": DB_PATH.name, "size_bytes": DB_PATH.stat().st_size, **inspect_db(DB_PATH)},
              backup_dir=str(BACKUP_DIR))


@app.post("/api/backups")
@require_auth(["Admin"])
def make_backup():
    with BACKUP_LOCK:
        meta = create_backup(json_body().get("note"))
    return ok(message=f"Đã sao lưu và kiểm tra bản sao: {meta['name']}", backup=meta), 201


@app.post("/api/backups/<name>/restore")
@require_auth(["Admin"])
def restore_backup(name):
    """Phục hồi CSDL từ bản sao lưu và KIỂM TRA kết quả: toàn vẹn, khóa ngoại, số dòng từng bảng khớp bản sao lưu."""
    path = BACKUP_DIR / name
    if not BACKUP_NAME.match(name) or not path.is_file():
        return fail("Không tìm thấy bản sao lưu!", 404)
    with BACKUP_LOCK:
        meta = backup_meta(path)
        if meta.get("sha256") and sha256_of(path) != meta["sha256"]:
            return fail("Bản sao lưu đã bị thay đổi sau khi tạo (sai mã băm SHA-256), không phục hồi.", 409)
        source_info = inspect_db(path)
        if source_info["integrity"] != "ok":
            return fail(f"Bản sao lưu bị lỗi toàn vẹn ({source_info['integrity']}), không phục hồi.", 409)
        safety = create_backup(f"Tự động trước khi phục hồi {name}", tag="truoc-phuc-hoi")
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(DB_PATH)) as target:
            source.backup(target)
        restored = inspect_db(DB_PATH)
    mismatched = {t: {"backup": source_info["counts"][t], "restored": restored["counts"][t]}
                  for t in CHECK_TABLES if source_info["counts"][t] != restored["counts"][t]}
    verified = restored["integrity"] == "ok" and not restored["foreign_key_errors"] and not mismatched
    return ok(message="Phục hồi thành công và đã kiểm tra dữ liệu." if verified else "Phục hồi xong nhưng kiểm tra không khớp!",
              verified=verified, restored_from=name, safety_backup=safety["name"],
              verification={"integrity": restored["integrity"], "foreign_key_errors": restored["foreign_key_errors"],
                            "counts_backup": source_info["counts"], "counts_after_restore": restored["counts"], "mismatched": mismatched})


@app.get("/api/backups/<name>/download")
@require_auth(["Admin"])
def download_backup(name):
    if not BACKUP_NAME.match(name) or not (BACKUP_DIR / name).is_file():
        return fail("Không tìm thấy bản sao lưu!", 404)
    return send_from_directory(BACKUP_DIR, name, as_attachment=True)


# ---------------------------------------------------------------- học máy

def thresholds():
    run = latest_run("classification")
    q = (run or {}).get("params", {}).get("thresholds_vnd", {})
    return q.get("q1"), q.get("q2")


@app.get("/api/predictions")
@require_auth()
def predictions():
    run = latest_run("regression")
    if run is None:
        return fail("Chưa có kết quả mô hình. Hãy chạy source-code/pipeline/train_models.py", 404)
    data = rows("""SELECT m.product_id, p.product_name, p.brand, c.category_name AS primary_category, m.actual_price_vnd AS current_price_vnd,
                          m.predicted_price_vnd, ABS(m.predicted_price_vnd - m.actual_price_vnd) AS absolute_error_vnd,
                          ABS(m.predicted_price_vnd - m.actual_price_vnd) * 100.0 / m.actual_price_vnd AS absolute_percentage_error,
                          m.actual_segment AS actual_price_group, m.predicted_segment AS classified_price_group
                   FROM ml_price_predictions m JOIN products p ON p.product_id = m.product_id
                   LEFT JOIN categories c ON c.category_id = p.category_id
                   WHERE m.split = 'test' ORDER BY p.product_name COLLATE NOCASE""")
    q1, q2 = thresholds()
    for r in data:  # nhóm giá suy ra từ giá dự đoán của mô hình hồi quy
        price = r["predicted_price_vnd"]
        r["predicted_price_group"] = None if q1 is None else SEGMENTS[0] if price <= q1 else SEGMENTS[1] if price <= q2 else SEGMENTS[2]
    test = run["metrics"].get("test", {})
    clf = latest_run("classification")
    return ok(total=len(data), predictions=data, thresholds={"q1_vnd": q1, "q2_vnd": q2},
              metrics={"model": run["model_name"], **test},
              model_comparison=all_runs("regression"),
              classification={"model": clf["model_name"], **clf["metrics"].get("test", {}), "comparison": all_runs("classification")} if clf else None,
              feature_importance={t: rows("SELECT feature, importance FROM ml_feature_importance WHERE task = ? ORDER BY importance DESC", (t,))
                                  for t in ("regression", "classification")},
              trained_at=run["trained_at"])


def cluster_products():
    return rows("""SELECT v.product_id, v.product_name, v.brand, v.category AS primary_category, v.retailer_id, v.source,
                          v.current_price_vnd, v.discount_percent, v.rating, v.review_count, m.cluster
                   FROM v_products v LEFT JOIN ml_clusters m ON m.product_id = v.product_id""")


@app.get("/api/clusters")
@require_auth()
def clusters():
    products = cluster_products()
    counts = Counter(p["cluster"] for p in products if p["cluster"] is not None)
    total = len(products)
    summary = [{"cluster": c, "count": n, "percentage": round(n / total * 100, 2)} for c, n in sorted(counts.items())]
    return jsonify({"success": True, "total_products": total, "total_clusters": len(summary),
                    "unclustered": total - sum(counts.values()), "clusters": summary, "products": products})


@app.get("/api/clusters/summary")
@require_auth()
def cluster_summary():
    products = [p for p in cluster_products() if p["cluster"] is not None]
    total = len(products) or 1
    data = []
    for c in sorted({p["cluster"] for p in products}):
        group = [p for p in products if p["cluster"] == c]
        ratings = [p["rating"] for p in group]
        top = lambda key: (Counter(p[key] for p in group if p[key]).most_common(1) or [(None, 0)])[0][0]
        data.append({
            "cluster": c, "product_count": len(group), "listing_share_percent": len(group) / total * 100,
            "median_price_vnd": median([p["current_price_vnd"] for p in group]),
            "mean_price_vnd": mean([p["current_price_vnd"] for p in group]),
            "median_discount_percent": median([p["discount_percent"] for p in group]),
            "median_rating": median(ratings), "rating_missing_percent": sum(r is None for r in ratings) / len(group) * 100,
            "median_review_count": median([p["review_count"] for p in group]),
            "top_category": top("primary_category") or "Không rõ", "top_retailer": top("retailer_id"),
        })
    return jsonify({"success": True, "data": data, "columns": list(data[0]) if data else []})


@app.get("/api/clusters/features")
@require_auth()
def cluster_features():
    run = latest_run("clustering")
    if run is None:
        return jsonify({"success": False, "message": "Chưa có kết quả phân cụm"}), 404
    labels = {"price_log": "Giá (log)", "discount": "Mức giảm giá", "rating": "Rating", "review_count_log": "Số lượt đánh giá (log)",
              "category_count": "Số danh mục", "category": "Danh mục", "product_type": "Loại sản phẩm", "retailer_id": "Nhà bán lẻ"}
    features = [{"feature": f, "label": labels.get(f, f), "type": "numeric"} for f in run["params"].get("numeric", [])]
    features += [{"feature": f, "label": labels.get(f, f), "type": "categorical"} for f in run["params"].get("categorical", [])]
    return jsonify({"success": True, "k": run["params"].get("k"), "silhouette": run["metrics"].get("silhouette"),
                    "model_selection": run["metrics"].get("model_selection", []), "data": features, "trained_at": run["trained_at"]})


@app.get("/api/anomalies")
@require_auth()
def anomalies():
    run = latest_run("anomaly")
    if run is None:
        return fail("Chưa có kết quả phát hiện bất thường. Hãy chạy train_models.py", 404)
    data = rows("""SELECT v.product_id, v.product_name, v.brand, v.category, v.retailer_id, v.source, v.product_url,
                          v.current_price_vnd, v.listed_price_vnd, v.discount_percent, v.rating, v.review_count,
                          a.anomaly_score, a.is_anomaly, a.reason
                   FROM ml_anomalies a JOIN v_products v ON v.product_id = a.product_id ORDER BY a.anomaly_score""")
    for r in data:
        r["is_anomaly"] = bool(r["is_anomaly"])
    category_median = {c: median([r["current_price_vnd"] for r in data if r["category"] == c]) for c in {r["category"] for r in data}}
    for r in data:
        r["category_median_price"] = category_median.get(r["category"])
    return ok(total=len(data), anomalies=sum(r["is_anomaly"] for r in data), products=data,
              model={"name": run["model_name"], **run["params"], **run["metrics"]}, trained_at=run["trained_at"])


# ---------------------------------------------------------------- frontend + lỗi

@app.get("/")
def index():
    return redirect("/login.html")


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/<path:filename>")
def frontend(filename):
    if filename.startswith("api/") or os.path.splitext(filename)[1].lower() not in STATIC_EXTENSIONS:
        return fail("Không tìm thấy!", 404)
    return send_from_directory(FRONTEND_DIR, filename)


@app.errorhandler(HTTPException)
def http_error(error):
    if request.path.startswith("/api/"):
        return fail(error.description or error.name, error.code)
    return error


@app.errorhandler(sqlite3.IntegrityError)
def integrity_error(error):
    return fail(f"Dữ liệu vi phạm ràng buộc CSDL: {error}", 400)


@app.errorhandler(Exception)
def server_error(error):
    app.logger.exception(error)
    return fail("Lỗi máy chủ, vui lòng thử lại!", 500)


ensure_database()

if __name__ == "__main__":
    host = os.environ.get("BEAUTY_HOST", "127.0.0.1")
    port = int(os.environ.get("BEAUTY_PORT", 5000))
    print("CSDL:", DB_PATH)
    print(f"BeautyPrice Intelligence: http://{host}:{port}/")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1", threaded=True)
