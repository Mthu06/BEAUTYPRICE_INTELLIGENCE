"""Kiểm thử công cụ thu thập (không cần mạng).

Chạy:  python source-code/tests/test_crawler.py
"""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source-code" / "crawler"))

import crawl  # noqa: E402

GUARDIAN_HTML = """<html><body><ol class="products list items product-items">
<li class="item product product-item"><div class="product-item-info">
  <a href="https://www.guardian.com.vn/shopby/hada-labo.html" class="product-item-brand-link">HADA LABO</a>
  <strong class="product name product-item-name"><a class="product-item-link" href="https://www.guardian.com.vn/kem-rua-mat-a.html">Kem Rửa Mặt A 80Gr</a></strong>
  <div class="rating-result" id="rating-result_1" title="90%"></div><span class="count">32 &nbsp;<span>Đánh giá</span></span>
  <div class="price-box"><span data-price-amount="75000" data-price-type="finalPrice" class="price-wrapper"></span>
  <span data-price-amount="92000" data-price-type="oldPrice" class="price-wrapper"></span><span class="percent-discount">-18 %</span></div>
</div></li>
<li class="item product product-item"><div class="product-item-info">
  <a href="#" class="product-item-brand-link">COCOON</a>
  <strong><a class="product-item-link" href="https://www.guardian.com.vn/combo-b.html">Combo B</a></strong>
  <div class="price-box"><span class="special-price"><span class="price">856,000₫</span></span></div>
</div></li>
</ol><p class="toolbar-amount"><span class="toolbar-number">2</span></p></body></html>"""


class FakeHttp:
    def __init__(self, body):
        self.body = body

    def get_text(self, url, method="GET"):
        return self.body


class CrawlerTest(unittest.TestCase):
    def test_product_id_matches_original_dataset(self):
        # Giá trị lấy từ dataset/raw/price_snapshots (1).csv: mã sản phẩm gốc của nhóm.
        url = "https://cocolux.com/tinh-chat-olay-duong-sang-da-niacinamide-vitamin-c-30ml-i.4902430759458"
        self.assertEqual(crawl.product_id("cocolux", url), "prod_000ead22008423b4")

    def test_robots_rules(self):
        http = crawl.Http(delay=0)
        rules = "User-agent: *\nDisallow: /*?\nAllow: /*?p=*\nDisallow: /*?p=*&*\nDisallow: /cart\n"
        http._raw = lambda *a, **k: (200, rules)
        cases = {"https://x.vn/a.html?p=2": True, "https://x.vn/a.html?p=2&q=1": False,
                 "https://x.vn/a.html?q=1": False, "https://x.vn/cart/add": False, "https://x.vn/a.html": True}
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(http.allowed(url), expected)

    def test_guardian_parser(self):
        _, records, total = crawl.Guardian().fetch(FakeHttp(GUARDIAN_HTML), "cham-soc-da-mat/sua-rua-mat", 1)
        self.assertEqual(total, 2)
        first, combo = records
        self.assertEqual(first["product_url"], "https://guardian.com.vn/kem-rua-mat-a.html")  # bỏ www. như dữ liệu gốc
        self.assertEqual((first["current_price_vnd"], first["listed_price_vnd"]), (75000, 92000))
        self.assertEqual((first["rating"], first["review_count"], first["brand"]), (4.5, 32, "HADA LABO"))
        self.assertEqual(combo["current_price_vnd"], 856000)  # giá dạng chữ của sản phẩm combo

    def test_clean_records(self):
        base = {"retailer_id": "hasaki", "category": "Serum", "collected_at": "2026-10-29T10:00:00+07:00", "brand": "X"}
        records = [
            {**base, "product_name": "  A  ", "product_url": "https://hasaki.vn/a-1.html", "current_price_vnd": 80000, "listed_price_vnd": 100000, "rating": 0},
            {**base, "category": "Sữa rửa mặt", "product_name": "A", "product_url": "https://hasaki.vn/a-1.html", "current_price_vnd": 80000, "listed_price_vnd": None},
            {**base, "product_name": "B", "product_url": "https://hasaki.vn/b-2.html", "current_price_vnd": 50000, "listed_price_vnd": 40000, "rating": 4.8},
            {**base, "product_name": "Không giá", "product_url": "https://hasaki.vn/c-3.html", "current_price_vnd": None, "listed_price_vnd": None},
        ]
        cleaned, rejected = crawl.clean_records(records)
        self.assertEqual((len(cleaned), rejected), (2, 1))
        a, b = cleaned
        self.assertEqual((a["product_name"], a["discount_percent"], a["rating"]), ("A", 20.0, None))
        self.assertEqual(a["categories"], {"Serum", "Sữa rửa mặt"})  # gộp sản phẩm xuất hiện ở 2 danh mục
        self.assertIsNone(b["listed_price_vnd"])  # niêm yết < giá bán -> bỏ


def review(rid, pid, spid, name=None, rating=5):
    return {"source": "hasaki", "source_product_id": spid, "review_id": rid, "product_id": pid, "review_key": f"hasaki:{spid}",
            "product_name": pid, "rating": rating, "review_text": "Tốt", "review_date": "2026-10-01T10:00:00",
            "review_date_raw": 1759287600, "is_bought": 1, "has_images": 0, "source_url": "https://hasaki.vn/x.html",
            "reviewer_name": name}


class ImportReviewsTest(unittest.TestCase):
    """Nạp review Hasaki: thêm review mới, nối biến thể dùng chung review, bổ sung tên; không bao giờ thêm sản phẩm."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript((ROOT / "source-code" / "pipeline" / "schema.sql").read_text(encoding="utf-8"))
        self.conn.execute("INSERT INTO retailers(retailer_id, retailer_name) VALUES ('hasaki', 'Hasaki')")
        for pid in ("A", "B"):  # 2 biến thể của cùng một sản phẩm
            self.conn.execute("INSERT INTO products(product_id, retailer_id, product_name, brand) VALUES (?, 'hasaki', ?, 'X')", (pid, pid))
        self.conn.execute("""INSERT INTO reviews(source, source_product_id, review_id, product_id, rating)
                             VALUES ('hasaki', '1', 'r1', 'A', 5)""")
        self.count = lambda sql: self.conn.execute(sql).fetchone()[0]

    def test_shared_review_is_linked_not_duplicated(self):
        found = [review("r1", "B", "2", "Lan N."), review("r2", "B", "2"), review("r1", "A", "1", "Lan N."),
                 review("r9", "KHONG-CO", "9")]
        added, named, linked = crawl.import_reviews(self.conn, found, "crawl_test", "2026-10-29T00:00:00")
        self.assertEqual((added, named, linked), (2, 1, 1))
        self.assertEqual(self.count("SELECT COUNT(*) FROM reviews WHERE review_id = 'r1'"), 1)  # r1 không bị lưu trùng
        self.assertEqual(self.count("SELECT COUNT(*) FROM review_links WHERE product_id = 'B'"), 1)  # B vẫn thấy r1
        self.assertEqual(self.count("SELECT reviewer_name FROM reviews WHERE review_id = 'r1'"), "Lan N.")
        self.assertIsNone(self.count("SELECT product_id FROM reviews WHERE review_id = 'r9'"))  # SP lạ: không thêm sản phẩm
        self.assertEqual(self.count("SELECT COUNT(*) FROM products"), 2)
        # chạy lại: không thêm / nối trùng
        self.assertEqual(crawl.import_reviews(self.conn, found, "crawl_test2", "2026-10-29T01:00:00"), (0, 0, 0))

    def test_names_only(self):
        added, named, linked = crawl.import_reviews(self.conn, [review("r1", "A", "1", "An T."), review("r2", "A", "1")],
                                                    "crawl_test", "2026-10-29T00:00:00", allow_new_reviews=False)
        self.assertEqual((added, named, linked), (0, 1, 0))
        self.assertEqual(self.count("SELECT COUNT(*) FROM reviews"), 1)


class CocoluxReviewTest(unittest.TestCase):
    """Review Cocolux: API trả trang bắt đầu từ 1, kèm totalRecord; nội dung nhiều dòng; tên tài khoản được rút gọn."""

    class Api:
        def __init__(self, pages):
            self.pages, self.calls = pages, []

        def get_json(self, url, method="GET", headers=None):
            self.calls.append((url, headers))
            page = int(url.split("&page=")[1].split("&")[0])
            data = {"data": self.pages.get(page, [])}
            return data, json.dumps(data)

    def test_paging_and_fields(self):
        item = lambda i: {"id": i, "rate": 5, "content": "Hương thơm:dịu\nLợi ích:sạch", "createdDate": "2026-01-23T23:28:20.123",
                          "fullname": "_nguyencham_0211", "mediaJson": '["a.jpg"]' if i == 1 else None, "totalRecord": 21}
        api = self.Api({1: [item(i) for i in range(1, 21)], 2: [item(21)]})
        with tempfile.TemporaryDirectory() as tmp:
            reviews, failed = crawl.crawl_cocolux_reviews(api, [("prod_x", "868", "SP", "https://cocolux.com/x", 21)], 0, Path(tmp))
        self.assertEqual((len(reviews), failed, len(api.calls)), (21, 0, 2))  # dừng khi đủ totalRecord
        self.assertEqual(api.calls[0][1]["X-Access-User"], "https://cocolux.com/")
        r = reviews[0]
        self.assertEqual((r["source"], r["review_key"], r["review_id"], r["reviewer_name"]), ("cocolux", "cocolux:868", "1", "N***"))
        self.assertEqual((r["review_text"], r["review_date"], r["has_images"], r["is_bought"]),
                         ("Hương thơm:dịu; Lợi ích:sạch", "2026-01-23T23:28:20", 1, None))

    def test_mask_name(self):
        self.assertEqual(crawl.mask_name("Nguyễn Văn An"), "Nguyễn V. A.")
        self.assertEqual(crawl.mask_name("___"), None)
        self.assertEqual(crawl.mask_name("a@b.com"), None)
        self.assertEqual(crawl.mask_name("0912345678"), None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
