"""Công cụ thu thập giá mỹ phẩm đa nguồn -> dataset/crawl/<lần chạy>/ + CSDL SQLite.

Nguồn hỗ trợ:
    hasaki    - API JSON công khai mà website dùng (/mobile/v3/main/products)
    cocolux   - API JSON danh sách sản phẩm (/Ajax/Content/PartialProduct)
    tgsf      - Thế Giới Skin Food, nền tảng Haravan (/collections/<handle>/products.json)
    guardian  - Magento, phân tích HTML trang danh mục (?p=N được robots.txt cho phép)
    watsons   - chỉ kiểm tra truy cập: website bật chống bot (Akamai) -> ghi 'blocked', KHÔNG vượt rào

Nguyên tắc: đọc và tuân thủ robots.txt, giãn cách giữa các yêu cầu, thử lại có giới hạn, lưu dữ liệu thô để truy vết.

Chạy (chỉ cần thư viện chuẩn của Python):
    python crawl.py --list                                   # xem nguồn và danh mục
    python crawl.py                                          # mọi nguồn, mọi danh mục, tối đa 3 trang/danh mục
    python crawl.py --sources hasaki,cocolux --categories serum --max-pages 0   # 0 = không giới hạn trang
    python crawl.py --dry-run                                # chỉ thu thập + lưu file, không ghi CSDL
"""
import argparse
import csv
import gzip
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source-code" / "pipeline"))
from build_database import brand_key, clean_text, extract_attributes, product_review_key  # noqa: E402

DB_PATH = Path(os.environ.get("BEAUTY_DB", ROOT / "dataset" / "beautyprice.db"))
CRAWL_DIR = ROOT / "dataset" / "crawl"
USER_AGENT = "Mozilla/5.0 (compatible; BeautyPriceBot/1.0; do an sinh vien - thu thap gia my pham)"

CATEGORIES = {
    "sua-rua-mat": "Sữa rửa mặt",
    "serum": "Serum",
    "kem-chong-nang": "Kem chống nắng",
    "tay-trang": "Tẩy trang",
    "sua-tam": "Sữa tắm",
    "tay-te-bao-chet": "Tẩy tế bào chết",
}


# ---------------------------------------------------------------- HTTP lịch sự

class Blocked(Exception):
    """Website chặn truy cập tự động (403/429, trang thử thách chống bot)."""


class Http:
    def __init__(self, delay=1.5, timeout=30, retries=2):
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self.last_request = {}
        self.robots = {}
        self.requests = 0

    def _robots_rules(self, host):
        """Đọc robots.txt (nhóm User-agent: *). Trả về [(allow, regex)]; không đọc được -> không có luật."""
        if host not in self.robots:
            rules, applies = [], False
            try:
                text = self._raw("GET", f"https://{host}/robots.txt", check_robots=False)[1]
            except Exception:
                text = ""
            for line in text.splitlines():
                line = line.split("#", 1)[0].strip()
                if ":" not in line:
                    continue
                key, value = (part.strip() for part in line.split(":", 1))
                key = key.lower()
                if key == "user-agent":
                    applies = value == "*" or "beautyprice" in value.lower()
                elif applies and key in ("allow", "disallow") and value:
                    pattern = "^" + re.escape(value).replace(r"\*", ".*").replace(r"\$", "$")
                    rules.append((key == "allow", len(value), re.compile(pattern)))
            self.robots[host] = rules
        return self.robots[host]

    def allowed(self, url):
        parts = urllib.parse.urlsplit(url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        matches = [(length, allow) for allow, length, rx in self._robots_rules(parts.netloc) if rx.match(path)]
        return not matches or max(matches)[1]  # luật khớp dài nhất thắng; bằng nhau thì Allow thắng

    def _raw(self, method, url, data=None, check_robots=True):
        if check_robots and not self.allowed(url):
            raise PermissionError(f"robots.txt không cho phép: {url}")
        host = urllib.parse.urlsplit(url).netloc
        wait = self.delay - (time.time() - self.last_request.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, method=method, data=data, headers={
            "User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.5",
            "Accept-Language": "vi-VN,vi;q=0.9", "X-Requested-With": "XMLHttpRequest"})
        for attempt in range(self.retries + 1):
            try:
                self.requests += 1
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    self.last_request[host] = time.time()
                    return response.status, response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as error:
                self.last_request[host] = time.time()
                body = error.read().decode("utf-8", errors="replace")
                if error.code >= 500 and attempt < self.retries:
                    time.sleep(2 ** attempt * 2)
                    continue
                return error.code, body
            except (urllib.error.URLError, TimeoutError) as error:
                self.last_request[host] = time.time()
                if attempt < self.retries:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise ConnectionError(f"Không kết nối được {host}: {error}") from error

    def get_text(self, url, method="GET"):
        status, body = self._raw(method, url, data=b"" if method == "POST" else None)
        if status in (401, 403, 429) or re.search(r"<title>\s*(Just a moment|Access Denied)", body[:5000], re.I):
            raise Blocked(f"HTTP {status} - website chặn truy cập tự động")
        if status != 200:
            raise ConnectionError(f"HTTP {status} tại {url}")
        return body

    def get_json(self, url, method="GET"):
        body = self.get_text(url, method)
        try:
            return json.loads(body), body
        except ValueError as error:
            raise ValueError(f"Phản hồi không phải JSON tại {url}") from error


# ---------------------------------------------------------------- nguồn dữ liệu

def to_price(value):
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


class Source:
    retailer_id = ""
    categories = {}   # khóa danh mục -> danh sách mã danh mục trên website
    page_size = 40
    method = "GET"
    raw_ext = "json"

    def page_url(self, code, page):
        raise NotImplementedError

    def parse(self, data):
        """Trả về (danh sách bản ghi, tổng số sản phẩm nếu website cho biết)."""
        raise NotImplementedError

    def fetch(self, http, code, page):
        """Tải 1 trang danh mục. Trả về (nội dung thô để lưu, bản ghi, tổng số)."""
        data, raw = http.get_json(self.page_url(code, page), self.method)
        records, total = self.parse(data)
        return raw, records, total


class Hasaki(Source):
    retailer_id = "hasaki"
    categories = {
        "sua-rua-mat": ["sua-rua-mat-c19"], "serum": ["serum-tinh-chat-c75"],
        "kem-chong-nang": ["chong-nang-da-mat-c11", "chong-nang-toan-than-c13"], "tay-trang": ["tay-trang-mat-c48"],
        "sua-tam": ["sua-tam-xa-bong-tam-c26"], "tay-te-bao-chet": ["tay-te-bao-chet-da-mat-c35", "tay-te-bao-chet-toan-than-c128"],
    }

    def page_url(self, code, page):
        return (f"https://hasaki.vn/mobile/v3/main/products?cate_path={code}&page={page}"
                f"&size={self.page_size}&has_meta_data=1&is_desktop=1")

    def parse(self, data):
        body = data.get("data") or {}
        records = []
        for p in body.get("products") or []:
            rating = p.get("rating") or {}
            count = rating.get("total") or 0
            records.append({
                "product_name": p.get("name"), "product_url": p.get("product_url"),
                "brand": (p.get("brand") or {}).get("name"),
                "current_price_vnd": to_price(p.get("price")), "listed_price_vnd": to_price(p.get("market_price")),
                "rating": rating.get("average") if count else None, "review_count": count,
                "promotion_text": p.get("promotion_text"), "availability": "in_stock" if (p.get("quantity") or 0) > 0 else "out_of_stock",
            })
        return records, (body.get("meta_data") or {}).get("products_total")


class Cocolux(Source):
    retailer_id = "cocolux"
    method = "POST"
    categories = {
        "sua-rua-mat": ["sua-rua-mat"], "serum": ["serum-tinh-chat"], "kem-chong-nang": ["kem-chong-nang"],
        "tay-trang": ["tay-trang"], "sua-tam": ["sua-tam"], "tay-te-bao-chet": ["tay-te-bao-chet-da-mat", "tay-da-chet-body"],
    }

    def page_url(self, code, page):
        return f"https://cocolux.com/Ajax/Content/PartialProduct?SeoUrl={code}&Page={page}&PageBrand=undefined&Sort=1&View="

    def parse(self, data):
        records = []
        for p in data.get("data") or []:
            count = p.get("totalRate") or 0
            records.append({
                "product_name": p.get("name"), "product_url": urllib.parse.urljoin("https://cocolux.com/", p.get("currentUrl") or ""),
                "brand": p.get("brandName"),
                "current_price_vnd": to_price(p.get("finalPrice")), "listed_price_vnd": to_price(p.get("price") or p.get("priceOld")),
                "rating": round(p["totalStar"] / count, 2) if count and p.get("totalStar") else None, "review_count": count,
                "promotion_text": p.get("promotionText"), "availability": None,
            })
        return records, data.get("total")


class TheGioiSkinFood(Source):
    retailer_id = "the_gioi_skin_food"
    page_size = 50
    categories = {
        "sua-rua-mat": ["sua-rua-mat"], "serum": ["serum-tinh-chat-duong"], "kem-chong-nang": ["kem-chong-nang"],
        "tay-trang": ["tay-trang"], "sua-tam": ["sua-tam"], "tay-te-bao-chet": ["tay-da-chet", "tay-da-chet-body"],
    }

    def page_url(self, code, page):
        return f"https://thegioiskinfood.com/collections/{code}/products.json?page={page}&limit={self.page_size}"

    def parse(self, data):
        records = []
        for p in data.get("products") or []:
            variants = p.get("variants") or [{}]
            v = next((x for x in variants if x.get("available")), variants[0])
            vendor = re.sub(r"_[A-Z]{1,3}$", "", p.get("vendor") or "")  # Haravan gắn hậu tố kho, VD "Simple_U"
            records.append({
                "product_name": p.get("title"), "product_url": f"https://thegioiskinfood.com/products/{p.get('handle')}",
                "brand": vendor, "current_price_vnd": to_price(v.get("price")), "listed_price_vnd": to_price(v.get("compare_at_price")),
                "rating": None, "review_count": None, "promotion_text": None,
                "availability": "in_stock" if v.get("available") else "out_of_stock",
            })
        return records, None


class Guardian(Source):
    """Magento: trang danh mục trả HTML có sẵn sản phẩm; robots.txt cho phép phân trang ?p=N."""
    retailer_id = "guardian"
    page_size = 20
    raw_ext = "html"
    categories = {
        "sua-rua-mat": ["cham-soc-da-mat/sua-rua-mat"], "serum": ["cham-soc-da-mat/serum-tinh-chat"],
        "kem-chong-nang": ["cham-soc-da-mat/chong-nang"], "tay-trang": ["cham-soc-da-mat/tay-trang"],
        "sua-tam": ["cham-soc-co-the/sua-tam"],
        "tay-te-bao-chet": ["cham-soc-da-mat/tay-te-bao-chet-da-mat", "cham-soc-co-the/tay-te-bao-chet-co-the"],
    }

    def page_url(self, code, page):
        return f"https://www.guardian.com.vn/{code}.html?p={page}"

    def fetch(self, http, code, page):
        page_html = http.get_text(self.page_url(code, page))
        start = page_html.find('<ol class="products list items product-items')
        listing = page_html[start: page_html.find("</ol>", start)] if start >= 0 else ""
        text = lambda pattern, block: html.unescape(re.sub(r"<[^>]+>", " ", (re.search(pattern, block, re.S) or [None, ""])[1])).strip()
        records = []
        for block in listing.split('<li class="item product product-item')[1:]:
            url = (re.search(r'class="product-item-link"\s+href="([^"]+)"', block) or [None, ""])[1]
            price = re.search(r'data-price-amount="([\d.]+)"\s+data-price-type="finalPrice"', block)
            old = re.search(r'data-price-amount="([\d.]+)"\s+data-price-type="oldPrice"', block)
            if not price:  # sản phẩm combo (bundle) chỉ có giá dạng chữ "856,000₫"
                box = block[block.find('class="price-box'):]
                price = re.search(r'<span class="price">([\d.,]+)', box.split('class="old-price"')[0])
                old = old or re.search(r'class="old-price".*?<span class="price">([\d.,]+)', box, re.S)
                price, old = ([None, m[1].replace(",", "").replace(".", "")] if m else None for m in (price, old))
            percent = re.search(r'class="rating-result"[^>]*title="([\d.]+)%"', block)  # 100% = 5 sao
            count = text(r'<span class="count">\s*([\d.,]+)', block)
            records.append({
                # dữ liệu gốc lưu URL không có "www." -> giữ đúng dạng để mã sản phẩm khớp
                "product_name": text(r'class="product-item-link"[^>]*>(.*?)</a>', block), "product_url": url.replace("://www.", "://"),
                "brand": text(r'class="product-item-brand-link"[^>]*>(.*?)</a>', block),
                "current_price_vnd": to_price(price[1]) if price else None, "listed_price_vnd": to_price(old[1]) if old else None,
                "rating": round(float(percent[1]) / 20, 2) if percent and count else None, "review_count": int(count.replace(",", "").replace(".", "")) if count else None,
                "promotion_text": text(r'<span class="percent-discount">(.*?)</span>', block) or None, "availability": None,
            })
        total = re.findall(r'class="toolbar-number">(\d+)<', page_html)
        # Magento trả lại trang cuối khi ?p vượt quá -> dừng nếu trang trùng trang trước
        if records and getattr(self, "_last_first_url", None) == (code, records[0]["product_url"]):
            records = []
        self._last_first_url = (code, records[0]["product_url"]) if records else None
        return page_html, records, int(total[-1]) if total else None


class AccessCheckOnly(Source):
    """Website bật chống bot: chỉ kiểm tra truy cập một lần rồi ghi nhật ký, không cố vượt qua."""
    home = ""

    def check(self, http):
        status, body = http._raw("GET", self.home)
        if status in (401, 403, 429) or re.search(r"Just a moment|Access Denied", body[:3000], re.I):
            raise Blocked(f"HTTP {status} - website bật chống bot, không thu thập tự động được")
        raise NotImplementedError("Website truy cập được nhưng chưa có bộ phân tích cho cấu trúc trang này")


class Watsons(AccessCheckOnly):
    retailer_id = "watsons"
    home = "https://www.watsons.vn/vi/"


SOURCES = {"hasaki": Hasaki, "cocolux": Cocolux, "tgsf": TheGioiSkinFood, "guardian": Guardian, "watsons": Watsons}


# ---------------------------------------------------------------- thu thập

def crawl(source, categories, http, max_pages, run_dir, collected_at):
    """Thu thập 1 nguồn. Trả về (bản ghi, nhật ký từng danh mục)."""
    records, logs = [], []
    raw_dir = run_dir / "raw" / source.retailer_id

    if isinstance(source, AccessCheckOnly):
        started = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            source.check(http)
        except Blocked as error:
            status, message = "blocked", str(error)
        except Exception as error:  # noqa: BLE001 - ghi nhận mọi lỗi vào nhật ký
            status, message = "failed", str(error)
        print(f"  [{source.retailer_id}] {status}: {message}")
        logs.append({"retailer_id": source.retailer_id, "category": "*", "started_at": started, "pages": 1,
                     "found": 0, "status": status, "error": message})
        return records, logs

    for key in categories:
        for code in source.categories.get(key, []):
            started = datetime.now().astimezone().isoformat(timespec="seconds")
            pages = found = 0
            status, message, total = "success", "", None
            page = 1
            while max_pages <= 0 or page <= max_pages:
                try:
                    raw, items, total = source.fetch(http, code, page)
                except Blocked as error:
                    status, message = "blocked", str(error)
                    break
                except PermissionError as error:
                    status, message = "skipped", str(error)
                    break
                except Exception as error:  # noqa: BLE001
                    status, message = ("partial" if pages else "failed"), str(error)
                    break
                if not items:
                    break
                pages += 1
                raw_name = f"{code.replace('/', '_')}_page_{page}.{source.raw_ext}.gz"
                raw_dir.mkdir(parents=True, exist_ok=True)
                with gzip.open(raw_dir / raw_name, "wt", encoding="utf-8") as file:
                    file.write(raw)
                for item in items:
                    item.update(retailer_id=source.retailer_id, category=CATEGORIES[key], collected_at=collected_at,
                                source_file=f"{source.retailer_id}/{raw_name}")
                records.extend(items)
                found += len(items)
                # biết tổng số -> chạy tới khi đủ; không biết -> trang thiếu là trang cuối
                if (total and found >= total) or (not total and len(items) < source.page_size):
                    break
                page += 1
            print(f"  [{source.retailer_id}] {code:<34} trang={pages:<3} sản phẩm={found:<5} {status} {message}")
            logs.append({"retailer_id": source.retailer_id, "category": code, "started_at": started, "pages": pages,
                         "found": found, "status": status, "error": message})
    return records, logs


# ---------------------------------------------------------------- làm sạch + nạp CSDL

def product_id(retailer_id, url):
    """Cùng công thức với dữ liệu gốc: prod_ + sha256('<retailer>|<url>')[:16] -> lần thu thập mới nối đúng sản phẩm cũ."""
    return "prod_" + hashlib.sha256(f"{retailer_id}|{url}".encode()).hexdigest()[:16]


def clean_records(records):
    """Chuẩn hóa, loại bản ghi lỗi, gộp sản phẩm xuất hiện ở nhiều danh mục trong cùng lần chạy."""
    result, rejected = {}, 0
    for r in records:
        name, url = clean_text(r.get("product_name")), clean_text(r.get("product_url"))
        price, listed = r.get("current_price_vnd"), r.get("listed_price_vnd")
        if not name or not url or not url.startswith("http") or not price:
            rejected += 1
            continue
        if listed is not None and listed < price:
            listed = None
        rating = r.get("rating")
        rating = round(float(rating), 2) if rating and 0 < float(rating) <= 5 else None
        pid = product_id(r["retailer_id"], url)
        if pid in result:
            result[pid]["categories"] |= set(r.get("categories") or {r["category"]})
            continue
        brand = clean_text(r.get("brand"))
        if not brand or len(brand) > 60 or brand == name or not brand_key(brand):  # combo nhiều hãng không có link thương hiệu
            brand = "Không rõ"
        result[pid] = {**r, "product_id": pid, "product_name": name[:300], "product_url": url, "brand": brand,
                       "listed_price_vnd": listed, "rating": rating,
                       "discount_percent": round((listed - price) / listed * 100, 2) if listed else None,
                       "categories": set(r.get("categories") or {r["category"]})}
    return list(result.values()), rejected


def save_csv(path, rows, fields):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (";".join(sorted(v)) if isinstance(v, set) else v) for k, v in row.items()})


def load_run(run_dir):
    """Đọc lại 1 lần thu thập đã lưu (để build_database.py dựng lại CSDL có cả dữ liệu thu thập mới)."""
    def num(value, cast=float):
        return cast(float(value)) if value not in (None, "") else None

    with open(run_dir / "snapshots.csv", encoding="utf-8-sig", newline="") as file:
        records = [{**r, "current_price_vnd": num(r["current_price_vnd"]), "listed_price_vnd": num(r["listed_price_vnd"]),
                    "discount_percent": num(r["discount_percent"]), "rating": num(r["rating"]),
                    "review_count": num(r["review_count"], int), "categories": set(filter(None, r["categories"].split(";")))}
                   for r in csv.DictReader(file)]
    logs = []
    if (run_dir / "collection_log.csv").exists():
        with open(run_dir / "collection_log.csv", encoding="utf-8-sig", newline="") as file:
            logs = [{**r, "pages": num(r["pages"], int), "found": num(r["found"], int)} for r in csv.DictReader(file)]
    run_at = records[0]["collected_at"] if records else (logs[0]["started_at"] if logs else "")
    return records, logs, run_dir.name, run_at


def import_records(conn, records, logs, run_id, run_at):
    """Nạp bản ghi đã làm sạch vào CSDL (dùng chung cho crawl.py và build_database.py)."""
    category_ids = dict(conn.execute("SELECT category_name, category_id FROM categories"))
    brands = {brand_key(b): b for (b,) in conn.execute("SELECT DISTINCT brand FROM products")}
    existing = {pid for (pid,) in conn.execute("SELECT product_id FROM products")}
    new_products = new_snapshots = 0
    with conn:
        for r in records:
            pid = r["product_id"]
            if pid not in existing:
                volume, weight, pack, is_combo = extract_attributes(r["product_name"])
                brand = brands.setdefault(brand_key(r["brand"]), r["brand"])
                primary = category_ids.get(sorted(r["categories"])[0])
                conn.execute("""INSERT INTO products(product_id, retailer_id, product_name, brand, category_id, product_type, product_url,
                                                     review_key, volume_ml, weight_g, pack_count, is_combo, data_origin)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'scraped')""",
                             (pid, r["retailer_id"], r["product_name"], brand, primary, "bundle" if is_combo else "unknown", r["product_url"],
                              product_review_key(r["retailer_id"], r["product_url"]), volume, weight, pack, is_combo))
                existing.add(pid)
                new_products += 1
            for name in r["categories"]:
                if name in category_ids:
                    conn.execute("INSERT OR IGNORE INTO product_categories VALUES (?,?)", (pid, category_ids[name]))
            snapshot_id = "snap_" + hashlib.sha256(f"{pid}|{r['collected_at']}".encode()).hexdigest()[:16]
            new_snapshots += conn.execute(
                """INSERT OR IGNORE INTO price_snapshots(snapshot_id, product_id, current_price_vnd, listed_price_vnd, discount_percent,
                                                         rating, review_count, collected_at, source_file, data_origin)
                   VALUES (?,?,?,?,?,?,?,?,?, 'scraped')""",
                (snapshot_id, pid, r["current_price_vnd"], r["listed_price_vnd"], r["discount_percent"], r["rating"],
                 r["review_count"], r["collected_at"], r["source_file"])).rowcount
        finished = datetime.now().astimezone().isoformat(timespec="seconds")
        for i, log in enumerate(logs, 1):
            saved = sum(1 for r in records if r["retailer_id"] == log["retailer_id"])
            conn.execute("INSERT OR REPLACE INTO collection_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (f"{run_id}_{i:02d}_{log['retailer_id']}", log["retailer_id"], f"crawler/crawl.py [{log['category']}]",
                          log["started_at"], finished, log["pages"], log["found"], saved if log["status"] == "success" else None,
                          0, log["status"], log["error"] or None, "crawl"))
        conn.execute("INSERT INTO etl_log(run_at, step, table_name, rows_in, rows_out, rows_affected, note) VALUES (?,?,?,?,?,?,?)",
                     (run_at, f"Nạp lần thu thập {run_id} (crawler)", "price_snapshots", len(records), new_snapshots, new_products,
                      f"{new_products} sản phẩm mới"))
    return new_products, new_snapshots


def import_to_db(records, logs, run_id, run_at):
    if not DB_PATH.exists():
        sys.exit(f"Chưa có CSDL {DB_PATH}. Hãy chạy source-code/pipeline/build_database.py trước.")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        return import_records(conn, records, logs, run_id, run_at)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", default=",".join(SOURCES), help="danh sách nguồn, VD hasaki,cocolux")
    parser.add_argument("--categories", default=",".join(CATEGORIES), help="danh sách danh mục, VD serum,sua-tam")
    parser.add_argument("--max-pages", type=int, default=3, help="số trang tối đa mỗi danh mục (0 = không giới hạn)")
    parser.add_argument("--delay", type=float, default=1.5, help="giây chờ giữa 2 yêu cầu tới cùng website")
    parser.add_argument("--dry-run", action="store_true", help="chỉ thu thập và lưu file, không ghi CSDL")
    parser.add_argument("--list", action="store_true", help="liệt kê nguồn và danh mục rồi thoát")
    args = parser.parse_args()

    if args.list:
        for name, cls in SOURCES.items():
            kind = "kiểm tra truy cập" if issubclass(cls, AccessCheckOnly) else ", ".join(cls.categories)
            print(f"{name:<9} ({cls.retailer_id}): {kind}")
        return
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    unknown = [s for s in sources if s not in SOURCES] + [c for c in categories if c not in CATEGORIES]
    if unknown:
        sys.exit(f"Không biết: {', '.join(unknown)}. Dùng --list để xem lựa chọn.")

    now = datetime.now().astimezone()
    # chạy thử dùng tiền tố khác để build_database.py không nạp nhầm
    run_id = now.strftime(("dryrun" if args.dry_run else "crawl") + "_%Y%m%dT%H%M%S")
    collected_at = now.isoformat(timespec="seconds")
    run_dir = CRAWL_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    http = Http(delay=args.delay)
    print(f"Lần thu thập {run_id} -> {run_dir}")
    all_records, all_logs = [], []
    for name in sources:
        records, logs = crawl(SOURCES[name](), categories, http, args.max_pages, run_dir, collected_at)
        all_records += records
        all_logs += logs

    cleaned, rejected = clean_records(all_records)
    save_csv(run_dir / "snapshots.csv", cleaned, ["product_id", "retailer_id", "product_name", "brand", "categories", "product_url",
                                                  "current_price_vnd", "listed_price_vnd", "discount_percent", "rating", "review_count",
                                                  "promotion_text", "availability", "collected_at", "source_file"])
    save_csv(run_dir / "collection_log.csv", all_logs, ["retailer_id", "category", "started_at", "pages", "found", "status", "error"])
    print(f"Tổng: {len(all_records)} bản ghi, {len(cleaned)} sản phẩm hợp lệ (loại {rejected}), {http.requests} yêu cầu HTTP")

    if args.dry_run:
        print("--dry-run: không ghi CSDL.")
        return
    new_products, new_snapshots = import_to_db(cleaned, all_logs, run_id, collected_at)
    print(f"Đã nạp CSDL: +{new_snapshots} snapshot giá, +{new_products} sản phẩm mới.")
    if new_products:
        print("Sản phẩm mới chưa có kết quả mô hình -> chạy source-code/pipeline/train_models.py để cập nhật.")


if __name__ == "__main__":
    main()
