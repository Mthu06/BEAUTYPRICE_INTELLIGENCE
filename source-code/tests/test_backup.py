"""Kiểm thử SAO LƯU & PHỤC HỒI THỰC TẾ (không chỉ tạo tệp backup) trên BẢN SAO CSDL.

Kịch bản: sao lưu -> làm thay đổi dữ liệu (xóa, thêm, sửa giá) -> phục hồi -> kiểm tra dữ liệu quay về đúng như lúc sao lưu.
Chạy:  cd source-code/backend  &&  .venv/Scripts/python ../tests/test_backup.py
"""
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="beautyprice_backup_test_"))
shutil.copy(ROOT / "dataset" / "beautyprice.db", TMP / "test.db")
os.environ["BEAUTY_DB"] = str(TMP / "test.db")
os.environ["BEAUTY_BACKUP_DIR"] = str(TMP / "backups")
os.environ["BEAUTY_SCHEDULER"] = "0"
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


def variant_db(name, *sql):
    """Bản sao CSDL hiện tại đã chạy thêm vài lệnh SQL -> bytes của tệp (giả lập CSDL từ máy khác)."""
    path = TMP / name
    shutil.copy(TMP / "test.db", path)
    with closing(sqlite3.connect(path)) as conn:
        for statement in sql:
            conn.execute(statement)
        conn.commit()
    return path.read_bytes()


class UploadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = backend.app.test_client()
        login = lambda u, p: cls.client.post("/api/login", json={"username": u, "password": p}).get_json()["token"]
        cls.admin = {"Authorization": "Bearer " + login("admin", "Admin@123")}
        cls.user = {"Authorization": "Bearer " + login("user", "User@123")}

    def upload(self, content, filename="tu-may-khac.db", headers=None):
        return self.client.post("/api/backups/upload", headers=headers or self.admin, content_type="multipart/form-data",
                                data={"file": (io.BytesIO(content), filename)})

    def test_upload_then_restore(self):
        # CSDL "từ máy khác": ít hơn 1 sản phẩm. Tệp ~10 MB > giới hạn 1 MB của API JSON nhưng vẫn nhận.
        with closing(sqlite3.connect(TMP / "test.db")) as conn:
            victim = conn.execute("SELECT product_id FROM products ORDER BY product_id LIMIT 1").fetchone()[0]
        content = variant_db("other.db", "PRAGMA foreign_keys = ON", f"DELETE FROM products WHERE product_id = '{victim}'")
        response = self.upload(content)
        self.assertEqual(response.status_code, 201, response.get_json())
        meta = response.get_json()["backup"]
        self.assertEqual((meta["source"], meta["original_name"], meta["integrity"]), ("upload", "tu-may-khac.db", "ok"))
        self.assertRegex(meta["name"], r"_tai-len\.db$")
        expected = meta["counts"]["products"]
        self.assertEqual(expected, snapshot_of_db()[0]["products"] - 1)
        # Tải lên KHÔNG thay CSDL; chỉ khi phục hồi mới thay, và vẫn kiểm tra như bản sao lưu thường
        result = self.client.post(f"/api/backups/{meta['name']}/restore", headers=self.admin).get_json()
        self.assertTrue(result["verified"], result)
        self.assertEqual(snapshot_of_db()[0]["products"], expected)
        # Quay lại bằng bản an toàn tự tạo trước khi phục hồi
        back = self.client.post(f"/api/backups/{result['safety_backup']}/restore", headers=self.admin).get_json()
        self.assertTrue(back["verified"])
        self.assertEqual(snapshot_of_db()[0]["products"], expected + 1)

    def test_old_backup_is_migrated(self):
        # Bản sao lưu cũ (trước khi có cột reviewer_name, bảng app_settings) vẫn nhận và được bổ sung sau phục hồi
        content = variant_db("old.db", "ALTER TABLE reviews DROP COLUMN reviewer_name", "DROP TABLE app_settings")
        response = self.upload(content, "ban-cu.sqlite")
        self.assertEqual(response.status_code, 201, response.get_json())
        result = self.client.post(f"/api/backups/{response.get_json()['backup']['name']}/restore", headers=self.admin).get_json()
        self.assertTrue(result["verified"])
        with closing(sqlite3.connect(TMP / "test.db")) as conn:
            self.assertIn("reviewer_name", {r[1] for r in conn.execute("PRAGMA table_info(reviews)")})
            conn.execute("SELECT COUNT(*) FROM app_settings")
        self.assertEqual(self.client.get("/api/reviews", headers=self.user).status_code, 200)

    def test_upload_rejected(self):
        listing = lambda: sorted(p.name for p in (TMP / "backups").glob("*")) if (TMP / "backups").exists() else []
        before = listing()
        header = b"SQLite format 3\x00"
        cases = [
            (b"day khong phai sqlite" * 10, "x.db", 422, "không phải CSDL SQLite"),
            (header, "x.txt", 400, "Chỉ nhận"),
            (header + b"\x00" * 200, "hong.db", 422, "hỏng"),
            (variant_db("t1.db", "DROP TABLE ml_anomalies"), "thieu.db", 422, "thiếu bảng ml_anomalies"),
            (variant_db("t2.db", "ALTER TABLE collection_logs DROP COLUMN script_name"), "cot.db", 422, "thiếu cột script_name"),
            (variant_db("t3.db", "CREATE TRIGGER evil AFTER INSERT ON products BEGIN DELETE FROM reviews; END"), "trg.db", 422, "evil"),
            (variant_db("t4.db", "UPDATE users SET role = 'User'"), "noadmin.db", 422, "quản trị"),
        ]
        for content, filename, status, message in cases:
            with self.subTest(filename=filename):
                response = self.upload(content, filename)
                self.assertEqual(response.status_code, status, response.get_json())
                self.assertIn(message, response.get_json()["message"])
        self.assertEqual(self.upload(b"x", headers=self.user).status_code, 403)
        self.assertEqual(self.client.post("/api/backups/upload", headers=self.admin, data={}).status_code, 400)
        # Tệp bị từ chối không để lại gì trong thư mục sao lưu
        self.assertEqual(listing(), before)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
