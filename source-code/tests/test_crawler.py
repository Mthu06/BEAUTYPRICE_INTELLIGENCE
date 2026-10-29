"""Kiểm thử công cụ thu thập (không cần mạng).

Chạy:  python source-code/tests/test_crawler.py
"""
import sys
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
