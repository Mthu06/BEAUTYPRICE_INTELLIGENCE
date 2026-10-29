# Thiết kế cơ sở dữ liệu — BeautyPrice Intelligence

- **Hệ quản trị CSDL:** SQLite 3. CSDL là file `dataset/beautyprice.db`.
- **Lược đồ:** [`source-code/pipeline/schema.sql`](../source-code/pipeline/schema.sql).
- **Chương trình dựng CSDL:** [`source-code/pipeline/build_database.py`](../source-code/pipeline/build_database.py).

## 1. Lý do chọn SQLite

| Tiêu chí | SQLite |
|---|---|
| Cài đặt | Không cần cài. Python có sẵn module `sqlite3`. |
| Mang sang máy khác | Toàn bộ CSDL là 1 file (khoảng 9,6 MB). Chép thư mục dự án là chạy được. |
| Đủ cho bài toán | Khoảng 5,7 nghìn sản phẩm, 6,4 nghìn snapshot giá, 6,7 nghìn review, 1–2 người dùng ghi đồng thời. |
| Tính năng CSDL quan hệ | Khóa chính, khóa ngoại (`ON DELETE CASCADE / SET NULL`), `CHECK`, `UNIQUE`, chỉ mục, view, hàm cửa sổ (`ROW_NUMBER`), transaction. |
| Chuyển sang MySQL/PostgreSQL | Lược đồ dùng SQL chuẩn. Chỉ cần đổi kiểu `AUTOINCREMENT`, cú pháp `strftime` và phần kết nối trong `app.py`. |

## 2. Sơ đồ quan hệ (ERD)

```mermaid
erDiagram
    retailers ||--o{ products : "bán"
    categories ||--o{ products : "danh mục chính"
    products ||--o{ product_categories : "thuộc"
    categories ||--o{ product_categories : "gồm"
    products ||--|{ price_snapshots : "lịch sử giá"
    products ||--o{ reviews : "được đánh giá"
    retailers ||--o{ reviews : "nguồn"
    retailers ||--o{ collection_logs : "lần thu thập"
    products ||--o{ product_matching : "ứng viên đối chiếu"
    products ||--o| ml_price_predictions : "dự đoán giá"
    products ||--o| ml_clusters : "cụm"
    products ||--o| ml_anomalies : "điểm bất thường"

    retailers {
        TEXT retailer_id PK
        TEXT retailer_name
        TEXT country
        TEXT currency
        TEXT website_url
        INTEGER is_active
    }
    categories {
        INTEGER category_id PK
        TEXT category_name UK
    }
    products {
        TEXT product_id PK
        TEXT retailer_id FK
        TEXT product_name
        TEXT brand
        INTEGER category_id FK
        TEXT product_type
        TEXT product_url
        TEXT review_key
        REAL volume_ml
        REAL weight_g
        INTEGER pack_count
        INTEGER is_combo
        TEXT data_origin
        TEXT created_at
        TEXT updated_at
    }
    product_categories {
        TEXT product_id PK,FK
        INTEGER category_id PK,FK
    }
    price_snapshots {
        TEXT snapshot_id PK
        TEXT product_id FK
        REAL current_price_vnd
        REAL listed_price_vnd
        REAL discount_percent
        REAL discount_source
        REAL rating
        INTEGER review_count
        TEXT collected_at
        TEXT source_file
        TEXT data_origin
    }
    reviews {
        INTEGER review_pk PK
        TEXT source FK
        TEXT source_product_id
        TEXT review_id
        TEXT product_id FK
        REAL rating
        TEXT review_text
        TEXT review_date
        INTEGER is_bought
        INTEGER has_images
    }
    collection_logs {
        TEXT run_id PK
        TEXT retailer_id FK
        TEXT status
        INTEGER records_saved
    }
    product_matching {
        TEXT match_id PK
        TEXT match_group_id
        TEXT product_id FK
        TEXT match_status
    }
    ml_price_predictions {
        TEXT product_id PK,FK
        TEXT split
        REAL actual_price_vnd
        REAL predicted_price_vnd
        TEXT actual_segment
        TEXT predicted_segment
    }
    ml_clusters {
        TEXT product_id PK,FK
        INTEGER cluster
    }
    ml_anomalies {
        TEXT product_id PK,FK
        REAL anomaly_score
        INTEGER is_anomaly
        TEXT reason
    }
```

Các bảng không có quan hệ khóa ngoại:
- `users`: tài khoản và vai trò.
- `etl_log`: nhật ký làm sạch dữ liệu.
- `ml_runs`: các lần huấn luyện, tham số và chỉ số đánh giá.
- `ml_feature_importance`: độ quan trọng của đặc trưng.

## 3. Từ điển dữ liệu và quy tắc nghiệp vụ

### retailers — nhà bán lẻ (5 dòng)
Gồm Cocolux, Guardian, Hasaki, The Gioi Skin Food, Watsons. Khóa `retailer_id` là chuỗi viết thường, ví dụ `hasaki`.

### categories — danh mục (6 dòng)
Gồm Kem chống nắng, Serum, Sữa rửa mặt, Sữa tắm, Tẩy trang, Tẩy tế bào chết. Tên danh mục là `UNIQUE`.

### products — sản phẩm (listing)
Mỗi dòng là **một sản phẩm tại một nhà bán lẻ**. Cùng một sản phẩm bán ở 2 nơi là 2 dòng; việc đối chiếu chúng nằm ở bảng `product_matching`.

| Cột | Kiểu | Ràng buộc / quy tắc |
|---|---|---|
| `product_id` | TEXT | Khóa chính |
| `retailer_id` | TEXT | Khóa ngoại → `retailers`, bắt buộc |
| `product_name` | TEXT | Bắt buộc, 1–300 ký tự. Đã chuẩn Unicode NFC, bỏ ký tự vô hình, gộp khoảng trắng |
| `brand` | TEXT | Bắt buộc. Các cách viết khác hoa/thường được gộp về cách viết phổ biến nhất |
| `category_id` | INTEGER | Khóa ngoại → `categories`. Cho phép NULL khi danh mục không rõ |
| `product_type` | TEXT | Một trong `single`, `bundle`, `multi_pack`, `unknown` |
| `product_url` | TEXT | Chỉ chấp nhận `http(s)` |
| `review_key` | TEXT | Khóa nối với review: `hasaki:<id cuối URL>` hoặc `guardian:<URL chuẩn hóa>` |
| `volume_ml`, `weight_g`, `pack_count`, `is_combo` | | Trích từ tên sản phẩm (ví dụ "400ml", "800g", "Bộ 3 món", "Combo") |
| `data_origin` | TEXT | `scraped` (thu thập) hoặc `manual` (admin thêm) |

### price_snapshots — lịch sử giá
Mỗi lần thu thập, hoặc mỗi lần admin đổi giá, sinh **một dòng mới**. **Giá hiện tại** của sản phẩm là snapshot mới nhất (xem view `v_latest_snapshot`).

| Cột | Ràng buộc / quy tắc |
|---|---|
| `current_price_vnd` | `> 0` |
| `listed_price_vnd` | NULL hoặc `>= current_price_vnd`. Nếu giá niêm yết nhỏ hơn giá bán thì bỏ (NULL) |
| `discount_percent` | `= (niêm yết − bán) / niêm yết × 100`, làm tròn 2 chữ số. NULL khi không có giá niêm yết (không đoán) |
| `discount_source` | Giá trị % giảm gốc trên website, giữ lại để truy vết |
| `rating` | NULL hoặc trong khoảng 0–5. Rating = 0 nghĩa là "chưa có đánh giá" nên được ghi NULL |
| `review_count` | NULL hoặc `>= 0` |

### reviews — đánh giá của khách hàng
- `UNIQUE (source, source_product_id, review_id)` để loại trùng.
- `rating` nằm trong khoảng 1–5 và **giữ nửa sao** (Guardian có các mức 4.5, 3.5, 2.5).
- `review_date` được chuẩn hóa về ISO 8601 từ 2 định dạng gốc: "2025-09-27 17:17:59" và "22 tháng 4, 2025". Giá trị gốc được giữ ở `review_date_raw`.
- `product_id` được nối theo ID nguồn. Khi sản phẩm bị xóa thì cột này về NULL (`ON DELETE SET NULL`); review vẫn được giữ.

### users — người dùng
- `role` là `Admin` (xem, thêm, sửa, xóa) hoặc `User` (chỉ xem).
- Mật khẩu chỉ lưu dạng băm PBKDF2-SHA256.
- Lần chạy đầu, backend tự tạo `admin` và `user`.

### etl_log — nhật ký làm sạch
Mỗi bước làm sạch ghi lại: tên bước, bảng, số dòng vào, số dòng ra, số dòng bị tác động, ghi chú. Trang **Báo cáo** hiển thị bảng này.

### Bảng kết quả học máy (do `train_models.py` ghi)

| Bảng | Nội dung |
|---|---|
| `ml_runs` | Mỗi mô hình đã thử: tham số, chỉ số validation/test, cờ `is_selected` |
| `ml_price_predictions` | Giá dự đoán (hồi quy) và phân khúc dự đoán (phân loại) cho từng sản phẩm, kèm tập `train`/`validation`/`test` |
| `ml_clusters` | Cụm K-Means của từng sản phẩm |
| `ml_anomalies` | Điểm Isolation Forest, cờ bất thường, lý do giải thích |
| `ml_feature_importance` | Độ quan trọng đặc trưng của mô hình hồi quy và phân loại |

## 4. View

- `v_latest_snapshot`: snapshot mới nhất của mỗi sản phẩm, lấy bằng `ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY collected_at DESC)`.
- `v_products`: sản phẩm + tên nhà bán lẻ + danh mục + giá mới nhất. Website đọc từ view này.

## 4b. Tách bảng (reference) hay gộp (embed): lựa chọn theo cách truy vấn

Nếu dùng MongoDB, mỗi quan hệ sẽ phải chọn giữa **nhúng (embed)** dữ liệu con vào document cha, hoặc **tham chiếu (reference)** sang collection khác bằng khóa. Với SQLite, câu hỏi tương ứng là **tách thành bảng riêng nối bằng khóa ngoại** (reference), hay **gộp cột vào cùng bảng / đọc qua view phẳng** (embed). Mỗi lựa chọn dưới đây dựa trên cách website và mô hình thực sự truy vấn:

| Quan hệ | Lựa chọn | Lý do (theo truy vấn và quan hệ dữ liệu) |
|---|---|---|
| Sản phẩm → **lịch sử giá** (1–N, tăng liên tục) | **Reference**: bảng `price_snapshots` riêng | Mỗi lần thu thập hoặc admin đổi giá lại sinh thêm snapshot (hiện 10.424 dòng, tăng sau mỗi lần crawl). Nhúng vào sản phẩm sẽ làm bản ghi phình mãi. Ngoài ra cần truy vấn riêng lịch sử giá theo ngày (biểu đồ xu hướng, Q5 trong `queries.sql`) và lấy "giá mới nhất" bằng `ROW_NUMBER()` |
| Sản phẩm → **nhà bán lẻ** (N–1, chỉ 5 dòng, ít đổi) | **Reference**: `products.retailer_id` → `retailers` | Thông tin nhà bán lẻ (tên, website) dùng chung cho hàng nghìn sản phẩm. Tách bảng thì sửa một chỗ là đủ. View `v_products` "nhúng" sẵn tên nhà bán lẻ khi đọc |
| Sản phẩm ↔ **danh mục** (N–N) | **Reference**: bảng nối `product_categories`; danh mục chính lưu ở `products.category_id` | Một sản phẩm có thể thuộc nhiều danh mục (7.133 cặp cho 6.413 sản phẩm). Lọc theo danh mục là thao tác chính trên website, nên cần chỉ mục trên bảng nối |
| Sản phẩm → **review** (1–N, 6.673 dòng, văn bản dài) | **Reference**: `reviews.product_id` (cho phép NULL) | Review đến từ nguồn khác (Hasaki, Guardian), nối bằng ID nguồn, có 85 review chưa nối được với sản phẩm nào. Review cũng được thống kê độc lập theo nguồn (Q6). Xóa sản phẩm thì review vẫn giữ (`ON DELETE SET NULL`) |
| Giá mới nhất, % giảm, rating hiện tại | **Embed khi đọc**: view `v_products` | Gần như mọi màn hình chỉ cần "sản phẩm + giá hiện tại". View trả về một bản ghi phẳng như document đã nhúng, mà không phải lưu trùng dữ liệu |
| Thuộc tính trích từ tên (ml, g, số món, combo) | **Embed**: cột trong `products` | Quan hệ 1–1, luôn đọc cùng sản phẩm (đặc trưng cho mô hình), không có vòng đời riêng |
| Kết quả mô hình (dự đoán, cụm, bất thường) | **Reference**: các bảng `ml_*` khóa theo `product_id` | Được ghi lại toàn bộ mỗi lần huấn luyện. Tách bảng thì huấn luyện lại không phải sửa bảng sản phẩm |
| Nhật ký thu thập, nhật ký làm sạch | **Bảng riêng** `collection_logs`, `etl_log` | Dữ liệu vận hành, chỉ ghi thêm; truy vấn để báo cáo chất lượng dữ liệu |

### Ánh xạ dữ liệu thu thập → bảng

| Tệp CSV (`dataset/raw/`) | Bảng | Ghi chú |
|---|---|---|
| `products (1).csv` | `products` | Chuẩn hóa tên, gộp thương hiệu, trích thuộc tính |
| `price_snapshots (1).csv` | `price_snapshots` | Giá theo website và thời điểm; tính lại % giảm |
| `retailers.csv` | `retailers` | 5 nhà bán lẻ |
| `product_categories (2).csv` | `categories`, `product_categories` | Quan hệ N–N |
| `product_matching.csv` | `product_matching` | Ứng viên đối chiếu sản phẩm giữa các website |
| `collection_logs.csv` | `collection_logs` | Lịch sử các lần thu thập |
| `hasaki_reviews.csv`, `guardian_reviews.csv` | `reviews` | Đánh giá hợp lệ (rating 1–5, đã bỏ trùng) |
| `dataset/crawl/crawl_*/snapshots.csv` | `products`, `price_snapshots` | Các lần thu thập mới bằng crawler |

### Script import, truy vấn mẫu và kiểm tra

| Tệp | Nội dung |
|---|---|
| `source-code/pipeline/schema.sql` | Tạo bảng, khóa, ràng buộc CHECK, chỉ mục, view |
| `source-code/pipeline/build_database.py` | Import + làm sạch; in số bản ghi từng bảng; ghi `etl_log` |
| `source-code/pipeline/queries.sql` | 7 truy vấn mẫu: find, filter, projection, sort, limit, aggregation, lookup. Mỗi truy vấn kèm cú pháp MongoDB tương đương |
| `source-code/pipeline/verify_database.py` | Kiểm tra số bản ghi sau import (CSV so với CSDL), toàn vẹn, khóa ngoại; đối chiếu kết quả truy vấn với phép tính độc lập bằng Python thuần |
| `reports/KIEM_TRA_CSDL.md` | Kết quả kiểm tra (tự sinh khi chạy `verify_database.py`) |

## 5. Luồng dữ liệu

```mermaid
flowchart LR
    A[Website 5 nhà bán lẻ] -->|thu thập lần đầu| B[dataset/raw/*.csv]
    A -->|crawl.py<br/>thu thập định kỳ| F[dataset/crawl/crawl_*]
    F -->|nạp snapshot mới| C
    B -->|build_database.py<br/>làm sạch + chuẩn hóa| C[(dataset/beautyprice.db)]
    C -->|train_models.py<br/>scikit-learn| D[bảng ml_*<br/>+ dataset/models/*.joblib]
    D --> C
    C -->|Flask API app.py| E[Website: Tổng quan, Tra cứu/CRUD,<br/>Phân khúc, Dự đoán, Bất thường, Báo cáo]
    E -->|Admin thêm/sửa giá| C
```

## 6. Ví dụ truy vấn

```sql
-- Số sản phẩm, giá min / max / trung bình theo nhà bán lẻ (giá hiện tại)
SELECT source, COUNT(*) AS so_sp, MIN(current_price_vnd) AS min_gia, MAX(current_price_vnd) AS max_gia,
       ROUND(AVG(current_price_vnd)) AS gia_tb
FROM v_products GROUP BY source ORDER BY gia_tb DESC;

-- Sản phẩm có biến động giá qua các lần thu thập
SELECT p.product_name, COUNT(*) AS so_lan, MIN(s.current_price_vnd) AS thap_nhat, MAX(s.current_price_vnd) AS cao_nhat
FROM price_snapshots s JOIN products p USING (product_id)
GROUP BY s.product_id HAVING MAX(s.current_price_vnd) > MIN(s.current_price_vnd)
ORDER BY (MAX(s.current_price_vnd) - MIN(s.current_price_vnd)) * 1.0 / MIN(s.current_price_vnd) DESC LIMIT 10;

-- Điểm review trung bình theo sản phẩm (đã nối theo ID nguồn)
SELECT p.product_name, COUNT(r.review_pk) AS so_review, ROUND(AVG(r.rating), 2) AS diem_tb
FROM reviews r JOIN products p USING (product_id) GROUP BY r.product_id ORDER BY so_review DESC LIMIT 10;
```
