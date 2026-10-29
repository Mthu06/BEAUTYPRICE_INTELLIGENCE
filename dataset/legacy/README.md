# Dữ liệu ban đầu (giữ nguyên, chưa chỉnh sửa)

| Tệp | Nguồn gốc |
|---|---|
| `hasaki_products_pages_1_9.csv` | Tệp dữ liệu nằm trong thư mục `frontend/` của **source ban đầu**: 338 sản phẩm Hasaki thu thập từ trang danh mục 1–9 ngày 17/10/2026 (giá hiện tại, giá niêm yết, % giảm, rating, số lượt đánh giá, link sản phẩm, thời điểm thu thập). |

- **Giữ nguyên từng byte**, không chỉnh sửa. Mã SHA-256: `dfe7f21a88cb7714727dec4c7f95286fcabbc70a020dd02da67cbb5d4deeb5f1`.
- Đây là **bản thu thập thử nghiệm đầu tiên**. Dữ liệu dùng chính thức cho hệ thống nằm trong `dataset/raw/` và đã qua làm sạch.
- Tệp được đặt ngoài `dataset/raw/` để các script import (`build_database.py`) và EDA không đọc nhầm.
