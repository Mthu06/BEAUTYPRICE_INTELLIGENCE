"""Kiểm thử API backend trên BẢN SAO của CSDL (không đụng dataset/beautyprice.db).

Chạy:  cd source-code/backend  &&  .venv/Scripts/python ../tests/test_api.py   (Windows)
       cd source-code/backend  &&  .venv/bin/python ../tests/test_api.py       (macOS/Linux)
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="beautyprice_test_"))
shutil.copy(ROOT / "dataset" / "beautyprice.db", TMP / "test.db")
os.environ["BEAUTY_DB"] = str(TMP / "test.db")
sys.path.insert(0, str(ROOT / "source-code" / "backend"))

import app as backend  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = backend.app.test_client()
        login = lambda u, p: cls.client.post("/api/login", json={"username": u, "password": p}).get_json()["token"]
        cls.admin = {"Authorization": "Bearer " + login("admin", "Admin@123")}
        cls.user = {"Authorization": "Bearer " + login("user", "User@123")}

    def test_auth(self):
        self.assertEqual(self.client.get("/api/products").status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={"username": "admin", "password": "sai"}).status_code, 401)
        self.assertEqual(self.client.post("/api/login", json=[1, 2]).status_code, 400)
        self.assertEqual(self.client.post("/api/products", json={}, headers=self.user).status_code, 403)

    def test_read_endpoints(self):
        for path in ["/api/products", "/api/reviews", "/api/price-statistics", "/api/price-trend", "/api/lookups",
                     "/api/data-quality", "/api/predictions", "/api/clusters", "/api/clusters/summary",
                     "/api/clusters/features", "/api/anomalies"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers=self.user).status_code, 200)
        products = self.client.get("/api/products", headers=self.user).get_json()
        self.assertGreater(products["total"], 5000)
        self.assertTrue(all(p["current_price_vnd"] > 0 for p in products["products"]))

    def test_validation(self):
        base = {"product_name": "SP thử", "brand": "Test", "retailer_id": "hasaki", "current_price_vnd": 100000}
        cases = [({**base, "retailer_id": "khong-co"}, "Nhà bán lẻ"),
                 ({**base, "listed_price_vnd": 50000}, "Giá niêm yết"),
                 ({**base, "current_price_vnd": 0}, "Giá hiện tại"),
                 ({**base, "product_url": "javascript:alert(1)"}, "Link"),
                 ({**base, "product_name": ""}, "Tên sản phẩm")]
        for body, message in cases:
            with self.subTest(message=message):
                response = self.client.post("/api/products", json=body, headers=self.admin)
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, response.get_json()["message"])

    def test_crud_keeps_price_history(self):
        body = {"product_name": "SP thử CRUD", "brand": "Test", "retailer_id": "hasaki", "category": "Serum",
                "current_price_vnd": "80.000", "listed_price_vnd": "100.000"}
        created = self.client.post("/api/products", json=body, headers=self.admin)
        self.assertEqual(created.status_code, 201)
        product = created.get_json()["product"]
        self.assertEqual(product["discount_percent"], 20.0)
        pid = product["id"]

        self.client.put(f"/api/products/{pid}", json={"product_name": "SP thử đổi tên"}, headers=self.admin)
        self.assertEqual(len(self.client.get(f"/api/products/{pid}", headers=self.admin).get_json()["history"]), 1,
                         "đổi tên không được sinh snapshot giá")
        self.client.put(f"/api/products/{pid}", json={"current_price_vnd": 70000}, headers=self.admin)
        detail = self.client.get(f"/api/products/{pid}", headers=self.admin).get_json()
        self.assertEqual(len(detail["history"]), 2, "đổi giá phải thêm snapshot mới")
        self.assertEqual(detail["product"]["current_price_vnd"], 70000)
        self.assertEqual(detail["product"]["discount_percent"], 30.0)

        self.assertEqual(self.client.delete(f"/api/products/{pid}", headers=self.admin).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/products/{pid}", headers=self.admin).status_code, 404)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
