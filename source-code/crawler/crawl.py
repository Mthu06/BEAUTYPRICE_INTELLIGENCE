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
    python crawl.py --sources hasaki --categories "" --reviews --review-pages 0   # chỉ lấy review Hasaki (kèm tên rút gọn)

Website: trang "Thu thập dữ liệu" (Admin) gọi hàm run() của file này, chạy nền và có lịch tự động.
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
CRAWL_DIR = Path(os.environ.get("BEAUTY_CRAWL_DIR", ROOT / "dataset" / "crawl"))
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

class Stopped(Exception):
    """Người dùng yêu cầu dừng lần thu thập."""


def check_stop(stop):
    if stop is not None and stop.is_set():
        raise Stopped("Đã dừng theo yêu cầu")


def crawl(source, categories, http, max_pages, run_dir, collected_at, log=print, stop=None):
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
        log(f"[{source.retailer_id}] {status}: {message}")
        logs.append({"retailer_id": source.retailer_id, "category": "*", "started_at": started, "pages": 1,
                     "found": 0, "status": status, "error": message})
        return records, logs

    for key in categories:
        for code in source.categories.get(key, []):
            check_stop(stop)
            started = datetime.now().astimezone().isoformat(timespec="seconds")
            pages = found = 0
            status, message, total = "success", "", None
            page = 1
            while max_pages <= 0 or page <= max_pages:
                if stop is not None and stop.is_set():
                    status, message = "stopped", "Đã dừng theo yêu cầu"
                    break
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
            log(f"[{source.retailer_id}] {code}: {pages} trang, {found} sản phẩm - {status} {message}".rstrip())
            logs.append({"retailer_id": source.retailer_id, "category": code, "started_at": started, "pages": pages,
                         "found": found, "status": status, "error": message})
    return records, logs


# ---------------------------------------------------------------- review Hasaki (kèm tên người đánh giá, rút gọn)

def mask_name(name):
    """Tên hiển thị rút gọn để bảo vệ dữ liệu cá nhân: 'Nguyễn Văn An' -> 'Nguyễn V. A.', 'Linh' -> 'L***'.
    Tên giống email/số điện thoại -> None (hiển thị 'Khách hàng')."""
    name = clean_text(name)
    if not name or "@" in name or len(re.sub(r"\D", "", name)) >= 6:
        return None
    words = [w for w in re.split(r"\s+", name) if w]
    if len(words) == 1:
        return words[0][0].upper() + "***"
    return " ".join([words[0]] + [w[0].upper() + "." for w in words[1:]])


def review_targets(limit=0):
    """Sản phẩm Hasaki cần lấy review: có lượt đánh giá trên website hoặc đã có review trong CSDL (nhiều review trước)."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT p.product_id, substr(p.review_key, 8) AS spid, p.product_name, p.product_url,
                   COALESCE(v.review_count, 0) + (SELECT COUNT(*) FROM reviews r WHERE r.product_id = p.product_id) AS weight
            FROM products p JOIN v_products v ON v.product_id = p.product_id
            WHERE p.review_key LIKE 'hasaki:%' AND weight > 0
            ORDER BY weight DESC, p.product_id""").fetchall()
    return rows[:limit] if limit > 0 else rows


def crawl_hasaki_reviews(http, targets, max_pages, run_dir, log=print, stop=None, page_size=20):
    """Lấy review qua API công khai /mobile/v3/detail/product/rating-reviews (robots.txt cho phép)."""
    raw_dir = run_dir / "raw" / "hasaki_reviews"
    reviews, failed = [], 0
    for index, (pid, spid, pname, url, _) in enumerate(targets, 1):
        if stop is not None and stop.is_set():
            log("[hasaki_reviews] Đã dừng theo yêu cầu")
            break
        page = fetched = 0
        while max_pages <= 0 or page < max_pages:
            page += 1
            api = (f"https://hasaki.vn/mobile/v3/detail/product/rating-reviews?product_id={spid}&page={page}"
                   f"&size={page_size}&sort=create&filter=filter_all&is_desktop=1")
            try:
                data, raw = http.get_json(api)
            except Exception as error:  # noqa: BLE001
                failed += 1
                log(f"[hasaki_reviews] {spid}: lỗi trang {page} - {error}")
                break
            body = data.get("data") or {}
            items = body.get("reviews") or []
            if not items:
                break
            raw_dir.mkdir(parents=True, exist_ok=True)
            with gzip.open(raw_dir / f"{spid}_page_{page}.json.gz", "wt", encoding="utf-8") as file:
                file.write(raw)
            for r in items:
                star = (r.get("rating") or {}).get("star") if isinstance(r.get("rating"), dict) else r.get("rating")
                created = r.get("created_at")
                try:
                    date = datetime.fromtimestamp(int(created)).isoformat(timespec="seconds")
                except (TypeError, ValueError):
                    date = None
                reviews.append({
                    "source": "hasaki", "source_product_id": spid, "review_id": str(r.get("id") or ""), "product_id": pid,
                    "review_key": f"hasaki:{spid}", "product_name": pname, "rating": star,
                    "review_text": clean_text(r.get("content")), "review_date": date, "review_date_raw": created,
                    "is_bought": 1 if r.get("is_bought") is True else 0 if r.get("is_bought") is False else None,
                    "has_images": 1 if r.get("images") else 0, "source_url": url,
                    "reviewer_name": mask_name(r.get("user_fullname")),
                })
            fetched += len(items)
            if fetched >= (body.get("total") or 0) or len(items) < page_size:
                break
        if index % 25 == 0 or index == len(targets):
            log(f"[hasaki_reviews] {index}/{len(targets)} sản phẩm, {len(reviews)} review")
    return reviews, failed


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


def clean_reviews(reviews):
    """Loại review thiếu khóa, rating ngoài 1-5, trùng (nguồn + sản phẩm + review_id)."""
    result, seen = [], set()
    for r in reviews:
        try:
            rating = float(r.get("rating"))
        except (TypeError, ValueError):
            continue
        key = (r.get("source"), r.get("source_product_id"), r.get("review_id"))
        if not all(key) or not 1 <= rating <= 5 or key in seen:
            continue
        seen.add(key)
        result.append({**r, "rating": round(rating, 1)})
    return result


SNAPSHOT_FIELDS = ["product_id", "retailer_id", "product_name", "brand", "categories", "product_url", "current_price_vnd",
                   "listed_price_vnd", "discount_percent", "rating", "review_count", "promotion_text", "availability",
                   "collected_at", "source_file"]
REVIEW_FIELDS = ["source", "source_product_id", "review_id", "product_id", "review_key", "product_name", "rating", "review_text",
                 "review_date", "review_date_raw", "is_bought", "has_images", "source_url", "reviewer_name"]


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

    records = []
    if (run_dir / "snapshots.csv").exists():
        with open(run_dir / "snapshots.csv", encoding="utf-8-sig", newline="") as file:
            records = [{**r, "current_price_vnd": num(r["current_price_vnd"]), "listed_price_vnd": num(r["listed_price_vnd"]),
                        "discount_percent": num(r["discount_percent"]), "rating": num(r["rating"]),
                        "review_count": num(r["review_count"], int), "categories": set(filter(None, r["categories"].split(";")))}
                       for r in csv.DictReader(file)]
    logs = []
    if (run_dir / "collection_log.csv").exists():
        with open(run_dir / "collection_log.csv", encoding="utf-8-sig", newline="") as file:
            logs = [{**r, "pages": num(r["pages"], int), "found": num(r["found"], int)} for r in csv.DictReader(file)]
    reviews = []
    if (run_dir / "reviews.csv").exists():
        with open(run_dir / "reviews.csv", encoding="utf-8-sig", newline="") as file:
            reviews = [{**r, "rating": num(r["rating"]), "is_bought": num(r["is_bought"], int), "has_images": num(r["has_images"], int),
                        "product_id": r["product_id"] or None, "reviewer_name": r["reviewer_name"] or None}
                       for r in csv.DictReader(file)]
    run_at = records[0]["collected_at"] if records else (logs[0]["started_at"] if logs else "")
    return records, logs, run_dir.name, run_at, reviews


def ensure_reviewer_column(conn):
    """CSDL cũ chưa có cột tên người đánh giá -> bổ sung (không mất dữ liệu)."""
    if "reviewer_name" not in {row[1] for row in conn.execute("PRAGMA table_info(reviews)")}:
        conn.execute("ALTER TABLE reviews ADD COLUMN reviewer_name TEXT")


def import_records(conn, records, logs, run_id, run_at, allow_new_products=False):
    """Nạp bản ghi đã làm sạch vào CSDL (dùng chung cho crawl.py và build_database.py).
    Mặc định chỉ thêm snapshot giá cho sản phẩm ĐÃ CÓ (giữ nguyên danh sách sản phẩm gốc);
    allow_new_products=True mới thêm sản phẩm lần đầu xuất hiện."""
    category_ids = dict(conn.execute("SELECT category_name, category_id FROM categories"))
    brands = {brand_key(b): b for (b,) in conn.execute("SELECT DISTINCT brand FROM products")}
    existing = {pid for (pid,) in conn.execute("SELECT product_id FROM products")}
    new_products = new_snapshots = 0
    if not allow_new_products:
        records = [r for r in records if r["product_id"] in existing]
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
            if allow_new_products:  # chế độ mặc định chỉ thêm giá, không đổi nhãn danh mục của sản phẩm gốc
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
        if records:
            conn.execute("INSERT INTO etl_log(run_at, step, table_name, rows_in, rows_out, rows_affected, note) VALUES (?,?,?,?,?,?,?)",
                         (run_at, f"Nạp lần thu thập {run_id} (crawler)", "price_snapshots", len(records), new_snapshots, new_products,
                          f"{new_products} sản phẩm mới"))
    return new_products, new_snapshots


def import_reviews(conn, reviews, run_id, run_at, allow_new_reviews=False):
    """Review đã có (cùng nguồn + sản phẩm + review_id) -> bổ sung tên người đánh giá.
    Mặc định KHÔNG thêm review mới (giữ nguyên bộ review gốc); allow_new_reviews=True mới thêm.
    Hasaki trả cùng một review cho các biến thể của một sản phẩm -> review_id đã có ở sản phẩm khác thì không thêm lại."""
    ensure_reviewer_column(conn)
    existing_products = {pid for (pid,) in conn.execute("SELECT product_id FROM products")}
    known_ids = {rid for (rid,) in conn.execute("SELECT review_id FROM reviews WHERE source = 'hasaki'")}
    added = named = 0
    with conn:
        for r in reviews:
            pid = r["product_id"] if r.get("product_id") in existing_products else None
            if allow_new_reviews and r["review_id"] not in known_ids:
                known_ids.add(r["review_id"])
                added += conn.execute(
                """INSERT OR IGNORE INTO reviews(source, source_product_id, review_id, product_id, review_key, product_name, category,
                                                 rating, review_text, review_date, review_date_raw, is_bought, has_images, source_url, reviewer_name)
                   VALUES (?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?)""",
                (r["source"], r["source_product_id"], r["review_id"], pid, r["review_key"], r["product_name"], r["rating"],
                 r["review_text"], r["review_date"], str(r["review_date_raw"] or ""), r["is_bought"], r["has_images"],
                 r["source_url"], r["reviewer_name"])).rowcount
            if r.get("reviewer_name"):
                named += conn.execute("""UPDATE reviews SET reviewer_name = ? WHERE source = ? AND source_product_id = ? AND review_id = ?
                                         AND reviewer_name IS NULL""",
                                      (r["reviewer_name"], r["source"], r["source_product_id"], r["review_id"])).rowcount
        if reviews:
            conn.execute("INSERT INTO etl_log(run_at, step, table_name, rows_in, rows_out, rows_affected, note) VALUES (?,?,?,?,?,?,?)",
                         (run_at, f"Nạp lần thu thập {run_id} (review)", "reviews", len(reviews), added, named,
                          f"{added} review mới, bổ sung tên cho {named} review đã có"))
    return added, named


def connect_db():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Chưa có CSDL {DB_PATH}. Hãy chạy source-code/pipeline/build_database.py trước.")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------- chạy một lần thu thập (dùng chung cho dòng lệnh và website)

def run(sources, categories, max_pages=3, delay=1.5, dry_run=False, reviews=False, review_pages=2, review_products=0,
        add_new_products=False, add_new_reviews=False, log=print, stop=None):
    """Thu thập giá (+ review Hasaki nếu chọn), lưu dataset/crawl/<run_id>/ và nạp CSDL. Trả về bảng tóm tắt."""
    unknown = [s for s in sources if s not in SOURCES] + [c for c in categories if c not in CATEGORIES]
    if unknown:
        raise ValueError(f"Không biết: {', '.join(unknown)}")
    now = datetime.now().astimezone()
    # chạy thử dùng tiền tố khác để build_database.py không nạp nhầm
    run_id = now.strftime(("dryrun" if dry_run else "crawl") + "_%Y%m%dT%H%M%S")
    collected_at = now.isoformat(timespec="seconds")
    run_dir = CRAWL_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    http = Http(delay=delay)
    log(f"Bắt đầu {run_id}: nguồn={','.join(sources) or '-'}; danh mục={','.join(categories) or '-'}; "
        f"tối đa {max_pages or 'không giới hạn'} trang; review Hasaki={'có' if reviews else 'không'}; "
        f"thêm SP mới={'có' if add_new_products else 'không'}; thêm review mới={'có' if add_new_reviews else 'không'}")
    summary = {"run_id": run_id, "status": "success", "records": 0, "products_valid": 0, "new_products": 0, "new_snapshots": 0,
               "reviews_found": 0, "reviews_added": 0, "reviews_named": 0, "requests": 0}

    all_records, all_logs = [], []
    try:
        for name in sources:
            check_stop(stop)
            records, logs = crawl(SOURCES[name](), categories, http, max_pages, run_dir, collected_at, log, stop)
            all_records += records
            all_logs += logs
    except Stopped:
        summary["status"] = "stopped"
    cleaned, rejected = clean_records(all_records)
    save_csv(run_dir / "snapshots.csv", cleaned, SNAPSHOT_FIELDS)
    save_csv(run_dir / "collection_log.csv", all_logs, ["retailer_id", "category", "started_at", "pages", "found", "status", "error"])
    summary.update(records=len(all_records), products_valid=len(cleaned))
    log(f"Giá: {len(all_records)} bản ghi, {len(cleaned)} sản phẩm hợp lệ (loại {rejected})")
    if not dry_run and (cleaned or all_logs):
        conn = connect_db()
        try:
            summary["new_products"], summary["new_snapshots"] = import_records(conn, cleaned, all_logs, run_id, collected_at, add_new_products)
        finally:
            conn.close()
        log(f"Đã nạp CSDL: +{summary['new_snapshots']} snapshot giá, +{summary['new_products']} sản phẩm mới")

    if reviews and summary["status"] != "stopped":
        targets = review_targets(review_products)
        log(f"Thu thập review Hasaki cho {len(targets)} sản phẩm (tối đa {review_pages or 'mọi'} trang x 20 review/sản phẩm)")
        found, failed = crawl_hasaki_reviews(http, targets, review_pages, run_dir, log, stop)
        found = clean_reviews(found)
        save_csv(run_dir / "reviews.csv", found, REVIEW_FIELDS)
        summary["reviews_found"] = len(found)
        if not dry_run and found:
            conn = connect_db()
            try:
                summary["reviews_added"], summary["reviews_named"] = import_reviews(conn, found, run_id, collected_at, add_new_reviews)
            finally:
                conn.close()
        log(f"Review: {len(found)} thu được, +{summary['reviews_added']} mới, bổ sung tên {summary['reviews_named']}"
            + (f", {failed} sản phẩm lỗi" if failed else ""))
        if stop is not None and stop.is_set():
            summary["status"] = "stopped"

    summary["requests"] = http.requests
    if summary["status"] != "stopped" and any(l["status"] not in ("success", "blocked") for l in all_logs):
        summary["status"] = "partial"
    log(f"Kết thúc {run_id}: {summary['status']}, {http.requests} yêu cầu HTTP"
        + (" (chạy thử, không ghi CSDL)" if dry_run else ""))
    if summary["new_products"]:
        log("Sản phẩm mới chưa có kết quả mô hình -> chạy source-code/pipeline/train_models.py để cập nhật.")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", default=",".join(SOURCES), help="danh sách nguồn, VD hasaki,cocolux")
    parser.add_argument("--categories", default=",".join(CATEGORIES), help="danh sách danh mục, VD serum,sua-tam (để trống = bỏ qua giá)")
    parser.add_argument("--max-pages", type=int, default=3, help="số trang tối đa mỗi danh mục (0 = không giới hạn)")
    parser.add_argument("--delay", type=float, default=1.5, help="giây chờ giữa 2 yêu cầu tới cùng website (tối thiểu 1)")
    parser.add_argument("--reviews", action="store_true", help="thu thập thêm review Hasaki (kèm tên người đánh giá rút gọn)")
    parser.add_argument("--review-pages", type=int, default=2, help="số trang review mỗi sản phẩm, 20 review/trang (0 = tất cả)")
    parser.add_argument("--review-products", type=int, default=50, help="số sản phẩm lấy review, ưu tiên nhiều đánh giá (0 = tất cả)")
    parser.add_argument("--add-new-products", action="store_true", help="thêm cả sản phẩm mới (mặc định chỉ cập nhật giá SP đã có)")
    parser.add_argument("--add-new-reviews", action="store_true", help="thêm cả review mới (mặc định chỉ bổ sung tên cho review đã có)")
    parser.add_argument("--dry-run", action="store_true", help="chỉ thu thập và lưu file, không ghi CSDL")
    parser.add_argument("--list", action="store_true", help="liệt kê nguồn và danh mục rồi thoát")
    args = parser.parse_args()
    if args.delay < 1:
        parser.error("--delay phải từ 1 giây trở lên (lịch sự với website)")

    if args.list:
        for name, cls in SOURCES.items():
            kind = "kiểm tra truy cập" if issubclass(cls, AccessCheckOnly) else ", ".join(cls.categories)
            print(f"{name:<9} ({cls.retailer_id}): {kind}")
        return
    split = lambda value: [x.strip() for x in value.split(",") if x.strip()]
    try:
        run(split(args.sources), split(args.categories), args.max_pages, args.delay, args.dry_run,
            args.reviews, args.review_pages, args.review_products, args.add_new_products, args.add_new_reviews,
            log=lambda m: print(f"  {m}"))
    except (ValueError, FileNotFoundError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
