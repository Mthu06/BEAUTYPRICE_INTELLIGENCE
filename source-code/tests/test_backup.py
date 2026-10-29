"""Kiểm thử SAO LƯU & PHỤC HỒI THỰC TẾ (không chỉ tạo tệp backup) trên BẢN SAO CSDL.

Kịch bản: sao lưu -> làm thay đổi dữ liệu (xóa, thêm, sửa giá) -> phục hồi -> kiểm tra dữ liệu quay về đúng như lúc sao lưu.
Chạy:  cd source-code/backend  &&  .venv/Scripts/python ../tests/test_backup.py
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="beautyprice_backup_test_"))
shutil.copy(ROOT / "dataset" / "beautyprice.db", TMP / "test.db")
os.environ["BEAUTY_DB"] = str(TMP / "test.db")
os.environ["BEAUTY_BACKUP_DIR"] = str(TMP / "backups")
sys.path.insert(0, str(ROOT / "source-code" / "backend"))

import app as backend  # noqa: E402


def snapshot_of_db():
    """Dấu vân tay dữ liệu: số dòng từng bảng + danh sách sản phẩm và giá mới nhất."""
    with sqlite3.connect(TMP / "test.db") as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in backend.CHECK_TABLES}
        prices = conn.execute("SELECT product_id, current_price_vnd FROM v_products ORDER BY product_id").fetchall()
    return counts, prices


class BackupRestoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = backend.app.test_client()
        login = lambda u, p: cls.client.post("/api/login", json={"username": u, "password": p}).get_json()["token"]
        cls.admin = {"Authorization": "Bearer " + login("admin", "Admin@123")}
        cls.user = {"Authorization": "Bearer " + login("user", "User@123")}

    def test_only_admin(self):
        self.assertEqual(self.client.get("/api/backups", headers=self.user).status_code, 403)
        self.assertEqual(self.client.post("/api/backups", json={}, headers=self.user).status_code, 403)
        self.assertEqual(self.client.get("/api/backups").status_code, 401)

    def test_reject_bad_names(self):
        for name in ["../test.db", "khong-ton-tai.db", "beautyprice_20260101T000000.db"]:
            with self.subTest(name=name):
                # "../" bị Flask chuẩn hóa trước khi khớp route -> 405; tên không hợp lệ -> 404. Không bao giờ 200.
                self.assertIn(self.client.post(f"/api/backups/{name}/restore", headers=self.admin).status_code, (404, 405))

    def test_backup_change_restore_verify(self):
        before = snapshot_of_db()

        # 1. Sao lưu: bản sao phải qua kiểm tra toàn vẹn ngay khi tạo
        created = self.client.post("/api/backups", json={"note": "Kiểm thử phục hồi"}, headers=self.admin)
        self.assertEqual(created.status_code, 201)
        backup = created.get_json()["backup"]
        self.assertEqual(backup["integrity"], "ok")
        self.assertEqual(backup["counts"], before[0])

        # 2. Thay đổi dữ liệu: xóa 1 sản phẩm, thêm 1 sản phẩm, sửa giá 1 sản phẩm
        products = self.client.get("/api/products", headers=self.admin).get_json()["products"]
        deleted, edited = products[0]["id"], products[1]["id"]
        deleted_snapshots = len(self.client.get(f"/api/products/{deleted}", headers=self.admin).get_json()["history"])
        self.assertEqual(self.client.delete(f"/api/products/{deleted}", headers=self.admin).status_code, 200)
        self.assertEqual(self.client.post("/api/products", json={"product_name": "SP thêm sau sao lưu", "brand": "Test",
                                                                 "retailer_id": "hasaki", "current_price_vnd": 99000},
                                          headers=self.admin).status_code, 201)
        edit = self.client.put(f"/api/products/{edited}", json={"current_price_vnd": 1234000, "listed_price_vnd": 1500000}, headers=self.admin)
        self.assertEqual(edit.status_code, 200, edit.get_json())
        self.assertNotEqual(snapshot_of_db(), before, "dữ liệu phải khác sau khi thay đổi")

        # 3. Phục hồi + kiểm tra do backend trả về
        restored = self.client.post(f"/api/backups/{backup['name']}/restore", headers=self.admin)
        self.assertEqual(restored.status_code, 200)
        result = restored.get_json()
        self.assertTrue(result["verified"], result["verification"])
        self.assertTrue(result["safety_backup"].endswith("_truoc-phuc-hoi.db"))

        # 4. Kiểm tra ĐỘC LẬP: dữ liệu quay về y hệt lúc sao lưu
        self.assertEqual(snapshot_of_db(), before)
        self.assertEqual(self.client.get(f"/api/products/{deleted}", headers=self.admin).status_code, 200, "sản phẩm đã xóa phải trở lại")

        # 5. Bản an toàn tự tạo trước khi phục hồi chứa trạng thái đã thay đổi -> có thể quay lại nếu phục hồi nhầm
        safety_counts = json.loads((TMP / "backups" / result["safety_backup"]).with_suffix(".json").read_text(encoding="utf-8"))["counts"]
        self.assertEqual(safety_counts["products"], before[0]["products"])  # -1 xóa +1 thêm
        # snapshot: mất theo SP bị xóa, +1 SP thêm mới, +1 lần sửa giá
        self.assertEqual(safety_counts["price_snapshots"], before[0]["price_snapshots"] - deleted_snapshots + 2)

    def test_tampered_backup_is_refused(self):
        created = self.client.post("/api/backups", json={}, headers=self.admin).get_json()["backup"]
        with open(TMP / "backups" / created["name"], "ab") as file:
            file.write(b"tampered")
        response = self.client.post(f"/api/backups/{created['name']}/restore", headers=self.admin)
        self.assertEqual(response.status_code, 409)
        self.assertIn("SHA-256", response.get_json()["message"])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
