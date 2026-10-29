# Giải thích code BeautyPrice Intelligence (tài liệu ôn vấn đáp)

Tài liệu đi từ **tổng quát → chi tiết**. Mỗi phần trả lời 3 câu: *file này làm gì*, *các hàm chính làm gì*, *cần lưu ý gì khi bị hỏi*.
Cuối tài liệu có **bộ câu hỏi vấn đáp thường gặp** kèm câu trả lời ngắn.

> Cách đọc nhanh: đọc Phần 1 và 2 để nắm bức tranh chung (10 phút), rồi đọc phần chi tiết của file mình phụ trách, cuối cùng luyện Phần 6.

---

## Phần 1. Tổng quan

### 1.1 Dự án làm gì

Hệ thống **thu thập – làm sạch – lưu trữ – phân tích – dự đoán giá mỹ phẩm** từ 5 nhà bán lẻ trực tuyến tại Việt Nam
(Hasaki, Watsons, Guardian, Cocolux, Thế Giới Skin Food), hiển thị trên website có đăng nhập và phân quyền.

### 1.2 Kiến trúc (4 tầng)

```
 (1) THU THẬP              (2) LÀM SẠCH + LƯU TRỮ           (3) PHÂN TÍCH / HỌC MÁY        (4) WEBSITE
 crawler/crawl.py   ──▶   pipeline/build_database.py ──▶   pipeline/train_models.py  ──▶  backend/app.py (Flask API)
 dataset/raw/*.csv  ──▶   dataset/beautyprice.db (SQLite)  ghi bảng ml_* + models/*.joblib     ▲
                          pipeline/verify_database.py                                          │ fetch JSON
                          (kiểm tra độc lập)                                              frontend/*.html + *.js
```

- **Một CSDL duy nhất**: `dataset/beautyprice.db` (SQLite). Mọi tầng đọc/ghi vào đây.
- **Backend** là Flask, chỉ trả JSON qua `/api/...` và phục vụ file tĩnh của frontend.
- **Frontend** là HTML + JavaScript thuần (không framework), vẽ biểu đồ bằng Chart.js đặt sẵn trong `frontend/vendor/` (không cần Internet).

### 1.3 Luồng dữ liệu một vòng

1. `crawl.py` gọi API/HTML công khai của website → lưu dữ liệu thô vào `dataset/crawl/<lần chạy>/` → nạp snapshot giá vào CSDL.
2. `build_database.py` dựng CSDL từ CSV gốc `dataset/raw/` (làm sạch, chuẩn hóa, ghi nhật ký từng bước vào `etl_log`).
3. `train_models.py` đọc CSDL, huấn luyện 4 nhóm mô hình, ghi kết quả vào các bảng `ml_*`.
4. `app.py` đọc CSDL, trả JSON cho các trang web; quản trị viên có thể sửa dữ liệu, thu thập mới, sao lưu/phục hồi.

### 1.4 Các con số phải nhớ (hay bị hỏi)

| Con số | Ý nghĩa | Lưu ý |
|---:|---|---|
| **5.657** | số **sản phẩm** (bảng `products`) | đây là "tổng sản phẩm" |
| **6.350** | số **bản ghi giá** (`price_snapshots`) = số cặp sản phẩm–danh mục (`product_categories`) | không phải số sản phẩm: khi cào theo danh mục, 569 sản phẩm nằm ở 2–4 danh mục nên được ghi nhiều lần (5.088×1 + 459×2 + 96×3 + 14×4 = 6.350) |
| **6.673** | số **review** gốc (Hasaki 6.263 + Guardian 410) | review chỉ lưu 1 lần dù hiện trên nhiều biến thể |
| **418** | số **thương hiệu** sau chuẩn hóa | gộp "L'Oreal", "LOREAL", "L’Oréal"… thành 1 |
| **5** | nhà bán lẻ | Guardian (Cloudflare) và Watsons (Akamai) hiện chặn bot |

### 1.5 Cách chạy

| Việc | Windows | macOS / Linux |
|---|---|---|
| Chạy website | nháy đúp `run.bat` | `./run.sh` |
| Tắt server | `stop.bat` | `./stop.sh` |
| Khởi động lại sau khi cập nhật code | `restart.bat` | `./restart.sh` |
| Dựng lại CSDL từ CSV gốc | `python source-code/pipeline/build_database.py --force` | như Windows |
| Huấn luyện lại mô hình | `python source-code/pipeline/train_models.py` | như Windows |
| Kiểm tra CSDL | `python source-code/pipeline/verify_database.py` | như Windows |

Tài khoản demo: `admin / Admin@123` (Quản trị viên), `user / User@123` (Người dùng).

---

## Phần 2. Bản đồ thư mục

```
beauty/
├─ run.bat / run.sh / stop.* / restart.*   chạy - tắt - khởi động lại server
├─ dataset/
│  ├─ raw/              CSV gốc của nhóm (KHÔNG sửa tay) - nguồn sự thật
│  ├─ crawl/            mỗi lần thu thập 1 thư mục: raw/*.gz, snapshots.csv, reviews.csv, collection_log.csv
│  ├─ beautyprice.db    CSDL SQLite đang dùng
│  ├─ models/           mô hình .joblib đã huấn luyện
│  └─ backups/          bản sao lưu (tạo từ website, không đưa lên git)
├─ source-code/
│  ├─ pipeline/         schema.sql, build_database.py, train_models.py, verify_database.py, queries.sql
│  ├─ crawler/          crawl.py (công cụ thu thập đa nguồn)
│  ├─ backend/          app.py (Flask API), requirements.txt
│  ├─ frontend/         9 trang HTML + JS/CSS, common.js dùng chung, vendor/chart.umd.min.js
│  ├─ analysis/         notebook/biểu đồ EDA (Giai đoạn 6)
│  └─ tests/            test_api.py, test_backup.py, test_crawler.py, e2e/ (test giao diện bằng trình duyệt)
└─ reports/             báo cáo: thiết kế CSDL, kiểm tra CSDL, kết quả mô hình, test case, sơ đồ màn hình, file này
```

---

## Phần 3. Tầng dữ liệu (pipeline)

### 3.1 `pipeline/schema.sql` – thiết kế CSDL

**Làm gì:** tạo toàn bộ bảng, khóa, ràng buộc, chỉ mục và view. Chạy được nhiều lần (`IF NOT EXISTS`).

| Nhóm | Bảng | Vai trò |
|---|---|---|
| Danh mục | `retailers`, `categories` | nhà bán lẻ, 6 danh mục |
| Sản phẩm | `products`, `product_categories` | 1 sản phẩm thuộc nhiều danh mục (quan hệ n–n) |
| Giá theo thời gian | `price_snapshots` | **mỗi lần thấy giá là 1 dòng** → có lịch sử giá |
| Đánh giá | `reviews`, `review_links` | `review_links` nối 1 review với các biến thể khác dùng chung review đó |
| Vận hành | `collection_logs`, `etl_log`, `users`, `app_settings`, `product_matching` | nhật ký thu thập, nhật ký làm sạch, tài khoản, cấu hình lịch |
| Học máy | `ml_runs`, `ml_price_predictions`, `ml_clusters`, `ml_anomalies`, `ml_feature_importance` | kết quả mô hình cho website đọc |
| View | `v_latest_snapshot`, `v_products` | giá **mới nhất** của mỗi sản phẩm (dùng `ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY collected_at DESC)`) |

**Lưu ý khi vấn đáp:**
- **Vì sao tách `price_snapshots` khỏi `products`?** Giá thay đổi theo thời gian; tách ra để giữ lịch sử, không ghi đè. Sửa giá trên web = **thêm** snapshot mới.
- **Ràng buộc toàn vẹn:** `CHECK` (giá > 0, rating 1–5, `product_url` bắt đầu bằng `http`…), `FOREIGN KEY` (`ON DELETE CASCADE` cho snapshot, `SET NULL` cho review), `UNIQUE (source, source_product_id, review_id)` chống review trùng.
- **Chỉ mục** trên các cột hay lọc/nối: `retailer_id`, `brand`, `category_id`, `review_key`, `product_id` của snapshot/review.
- **Vì sao SQLite?** 1 file, không cần cài máy chủ CSDL, mang sang máy khác chạy ngay; đủ cho ~10 nghìn dòng; vẫn có SQL chuẩn, khóa ngoại, view, window function. File `queries.sql` có ghi kèm câu MongoDB tương đương để so sánh.

### 3.2 `pipeline/build_database.py` – làm sạch và dựng CSDL

**Làm gì:** đọc CSV gốc trong `dataset/raw/`, làm sạch, nạp vào CSDL mới; mỗi bước làm sạch ghi 1 dòng vào `etl_log`
(bảng nào, vào bao nhiêu dòng, ra bao nhiêu, tác động bao nhiêu) → trang Báo cáo hiển thị lại quy trình.

**Hàm làm sạch (dùng chung, crawler cũng import):**

| Hàm | Việc |
|---|---|
| `clean_text` | chuẩn hóa Unicode (NFC), bỏ ký tự vô hình, gộp khoảng trắng |
| `parse_number` | đọc số kiểu VN "1.250.000đ", "1,25tr"… |
| `parse_bool`, `parse_review_date` | đọc True/yes/1; đổi ngày "22 tháng 4, 2025" hay epoch về ISO 8601 |
| `extract_attributes` | trích từ tên: dung tích ml, khối lượng g, số món, có phải combo không (đặc trưng cho học máy) |
| `brand_key` / `canonical_brands` | khóa so sánh thương hiệu (bỏ dấu, hoa/thường, ký tự đặc biệt) → gộp về 1 tên hiển thị → **418 thương hiệu** |
| `product_review_key` | khóa nối review với sản phẩm theo ID ở website nguồn |

**Lớp `Loader`** nạp theo thứ tự có phụ thuộc khóa ngoại:
`retailers` → `categories` → `products` → `product_categories` → `price_snapshots` → `reviews` → `collection_logs` → `product_matching`.

Quy tắc làm sạch quan trọng (đều có dòng tương ứng trong `etl_log`):
- Loại sản phẩm trùng/thiếu khóa; danh mục không hợp lệ → `NULL`.
- Giá ≤ 0 hoặc không đọc được → loại; **giá niêm yết < giá bán → bỏ giá niêm yết** (không hợp lý); **% giảm tính lại** = (niêm yết − bán) / niêm yết; thiếu dữ liệu → để `NULL`, **không đoán**.
- Rating = 0 nghĩa là chưa có đánh giá → `NULL` (không coi là 0 sao).
- Review: loại thiếu khóa, rating ngoài 1–5, trùng (nguồn + sản phẩm + review_id).

**Các hàm khác:**
- `seed_users` + `password_hash`: tạo 2 tài khoản demo, mật khẩu băm PBKDF2-SHA256 (600.000 vòng, cùng định dạng werkzeug).
- `import_crawl_runs`: **chỉ khi chạy `--with-crawl`** mới nạp lại các lần thu thập trong `dataset/crawl/`. Mặc định CSDL chỉ có dữ liệu gốc (5.657 sản phẩm) để khớp EDA và báo cáo.
- `build(db_path)`: dựng vào file tạm `.building`, xong mới đổi tên → không bao giờ để CSDL dở dang. `--force` giữ bản cũ thành `.bak`.

### 3.3 `pipeline/verify_database.py` + `queries.sql` – kiểm tra độc lập

**Làm gì:** chứng minh CSDL đúng bằng **cách tính thứ hai không dùng SQL**: đọc thẳng CSV bằng Python thuần, tính lại
số dòng từng bảng và kết quả các truy vấn Q1–Q7, so với kết quả SQL trong CSDL. Ghi báo cáo `reports/KIEM_TRA_CSDL.md`; có mục FAIL thì thoát mã 1.

| Truy vấn | Kiểu | Ý nghĩa |
|---|---|---|
| Q1 | find + filter + projection | sản phẩm Guardian giá > 1 triệu |
| Q2 | sort + limit | 10 sản phẩm đắt nhất |
| Q3 | aggregate theo nhà bán lẻ | số SP, min/max/trung bình giá |
| Q4 | filter + count | số SP giảm > 30% theo nhà bán lẻ |
| Q5 | aggregate lịch sử giá | số snapshot theo ngày, nhà bán lẻ |
| Q6 | aggregate review | số review, điểm TB, tỷ lệ đã mua theo nguồn |
| Q7 | lookup (join) + sort + limit | minh họa, không so sánh |

**Lưu ý:** script tự đọc `etl_log` để biết CSDL đã nạp những lần thu thập nào, rồi áp **đúng quy tắc** của crawler
(chỉ thêm snapshot cho sản phẩm đã có, review chống trùng theo (nguồn, review_id)). Nhờ đó vẫn PASS sau khi thu thập thêm.
Đã thử sửa tay CSDL (xóa 1 dòng, đổi 1 giá) → script báo FAIL đúng chỗ.

### 3.4 `pipeline/train_models.py` – học máy

**Làm gì:** 4 bài toán, mỗi bài ghi kết quả vào `ml_runs` (tham số, độ đo) và bảng kết quả riêng; lưu mô hình `.joblib`.

**Đặc trưng (features):**
- Phân loại (one-hot): `brand`, `category`, `product_type`, `retailer_id` – thương hiệu hiếm (< 5 SP) gộp "khác" (`min_frequency=5`).
- Số: số danh mục, rating, `log(1 + số review)`, `log(1 + ml)`, `log(1 + g)`, số món, combo.
- **Không dùng giá niêm yết / % giảm làm đặc trưng** khi dự đoán giá → tránh rò rỉ (leakage) vì chúng suy ra trực tiếp từ giá.

| Bài toán | Mô hình so sánh | Cách chọn | Kết quả lần huấn luyện hiện tại (tập test) |
|---|---|---|---|
| 1. Hồi quy giá (dự đoán `log(giá)`) | Dummy (trung vị), Ridge, Random Forest, Extra Trees | MAE nhỏ nhất trên **validation** | Random Forest: MAE ≈ 90.290đ, R² ≈ 0,54, MAPE ≈ 35% |
| 2. Phân loại phân khúc Thấp/TB/Cao | Dummy, Logistic, Random Forest, Extra Trees | F1-macro lớn nhất trên validation | Extra Trees: accuracy ≈ 0,735, F1-macro ≈ 0,73 |
| 3. Phân cụm | K-Means, k = 2…10 | silhouette lớn nhất | k = 7, silhouette ≈ 0,285 |
| 4. Bất thường | Isolation Forest, contamination 5% | — | 283 sản phẩm bất thường, kèm lý do |

**Lưu ý khi vấn đáp:**
- **Chia dữ liệu 60/20/20** (train/validation/test, `random_state=42`): chọn mô hình trên validation, **chỉ báo cáo test cho mô hình được chọn** → không "chọn theo test".
- **Ngưỡng phân khúc** (1/3 và 2/3 phân vị giá) tính **trên tập train**, rồi mới áp cho validation/test → tránh rò rỉ.
- Dự đoán `log(giá)` vì giá lệch phải mạnh (nhiều SP rẻ, ít SP rất đắt); dự đoán xong đổi ngược bằng `expm1`.
- Có **mô hình Dummy làm mốc**: mô hình thật phải tốt hơn hẳn Dummy mới có ý nghĩa.
- R² ≈ 0,54 nghĩa là giải thích được khoảng một nửa biến động giá; hạn chế vì thiếu thông tin như thành phần, xuất xứ, hình ảnh.
- Silhouette 0,285 = các cụm tách vừa phải (thang −1…1), hợp lý với dữ liệu thật nhiều chồng lấn.
- Isolation Forest: điểm càng thấp càng bất thường; "bất thường" là **cần rà soát** (VD giá 9.000đ với niêm yết 489.000đ do hàng cận date), không chắc chắn là sai.

---

## Phần 4. Công cụ thu thập – `crawler/crawl.py`

**Làm gì:** thu thập giá (và review) từ nhiều website, lưu dữ liệu thô để truy vết, rồi nạp vào CSDL.
Chỉ dùng thư viện chuẩn Python. Dùng được từ dòng lệnh **và** từ trang web "Thu thập dữ liệu" (website gọi hàm `run()`).

### 4.1 HTTP "lịch sự" – lớp `Http`
- `_robots_rules` / `allowed`: đọc `robots.txt`, áp luật `Allow/Disallow` (luật khớp dài nhất thắng). URL bị cấm → `PermissionError`, **không gửi**.
- `_raw`: giãn cách tối thiểu `delay` giây **giữa 2 yêu cầu tới cùng website**; lỗi 5xx/mất mạng thì thử lại có giới hạn (chờ tăng dần).
- `get_text`: gặp 401/403/429 hoặc trang "Just a moment / Access Denied" → ném `Blocked` (ghi trạng thái `blocked`, **không vượt rào**).
- User-Agent ghi rõ là bot đồ án sinh viên.

### 4.2 Các nguồn – lớp `Source` và lớp con
| Lớp | Cách lấy |
|---|---|
| `Hasaki` | API JSON `/mobile/v3/main/products` mà chính website dùng |
| `Cocolux` | API JSON `/Ajax/Content/PartialProduct` (POST); giữ mã nội bộ để lấy review |
| `TheGioiSkinFood` | nền tảng Haravan: `/collections/<mã>/products.json` |
| `Guardian` | đọc HTML trang danh mục (`?p=N` được robots cho phép); hiện bị Cloudflare chặn → `blocked` |
| `Watsons` (`AccessCheckOnly`) | chỉ kiểm tra truy cập 1 lần, ghi `blocked` (Akamai) |

Mỗi lớp khai báo `categories` (6 danh mục của dự án → mã danh mục trên website) và hàm `parse` đổi JSON/HTML thành bản ghi chung
(tên, URL, thương hiệu, giá, giá niêm yết, rating, số review…).

### 4.3 Vòng thu thập – `crawl()`
Với mỗi danh mục: tải lần lượt từng trang → lưu bản thô `.gz` → dừng khi đủ tổng số, trang thiếu, hết `max_pages`, bị chặn, hoặc người dùng bấm Dừng (`stop` event).
Mỗi danh mục ghi 1 dòng nhật ký (số trang, số SP, trạng thái).

### 4.4 Review
- `mask_name`: **chỉ lưu tên rút gọn** ("Nguyễn Văn An" → "Nguyễn V. A.", tên tài khoản → "N***"); tên giống email/số điện thoại → bỏ. Không lưu mã tài khoản.
- Hasaki: `review_targets` (chọn sản phẩm, **ưu tiên sản phẩm còn thiếu review nhiều nhất**) → `crawl_hasaki_reviews` (API `rating-reviews`).
- Cocolux: `cocolux_review_targets` (lấy mã nội bộ + số đánh giá từ API danh sách, không tải trang sản phẩm) → `crawl_cocolux_reviews` (API `getlistcommentbycontent`, trang bắt đầu từ 1).

### 4.5 Làm sạch và nạp – quy tắc nghiệp vụ quan trọng
- `product_id(retailer, url)` = `"prod_" + sha256("<retailer>|<url>")[:16]` – **cùng công thức với dữ liệu gốc** → lần thu thập mới tự nối đúng sản phẩm cũ, lịch sử giá liền mạch.
- `clean_records`: loại thiếu tên/URL/giá; niêm yết < bán → bỏ niêm yết; gộp SP xuất hiện ở nhiều danh mục trong cùng lần chạy.
- `import_records`: **mặc định chỉ thêm snapshot giá cho sản phẩm đã có** → danh sách 5.657 sản phẩm gốc không đổi; bật `add_new_products` mới thêm sản phẩm mới. Snapshot có khóa `sha256(product_id|thời điểm)` → chạy lại không bị trùng.
- `import_reviews`: review mới thì thêm; review đã có (cùng nguồn + `review_id`) mà xuất hiện ở **biến thể khác** → chỉ thêm 1 dòng vào `review_links` (không lưu trùng); chưa có tên → bổ sung tên rút gọn.
- `run()`: điều phối 1 lần chạy (giá → review), trả bảng tóm tắt; mã lần chạy `crawl_YYYYmmddTHHMMSS`; `--dry-run` dùng tiền tố `dryrun_` để không bị nạp nhầm.

**Lưu ý khi vấn đáp:**
- **Vì sao không lấy Guardian/Watsons?** Họ bật chống bot (Cloudflare/Akamai) và robots.txt của Guardian cấm `/review/`. Dự án cam kết tôn trọng robots.txt và không vượt cơ chế chống bot; dữ liệu Guardian/Watsons trong dự án là dữ liệu gốc thu thập trước đó.
- **Vì sao lưu dữ liệu thô?** Để truy vết, kiểm tra lại, và dựng lại CSDL (`build_database.py --with-crawl`) mà không cần gọi lại website.

---

## Phần 5. Website

### 5.1 `backend/app.py` – Flask API

**Cấu hình đầu file:** đường dẫn CSDL/sao lưu đọc từ biến môi trường (`BEAUTY_DB`, `BEAUTY_BACKUP_DIR`, `BEAUTY_PORT`…);
giới hạn body JSON 1 MB; CORS chỉ cho origin được khai báo; bảng quyền `PERMISSIONS` cho 2 vai trò.

**CSDL:** `ensure_database()` – chưa có CSDL thì tự dựng từ `dataset/raw/`; `migrate()` bổ sung bảng/cột mới cho CSDL cũ;
`db()` mở 1 kết nối cho mỗi request (bật `PRAGMA foreign_keys`), `close_db` đóng khi xong; `rows()` / `one()` chạy SQL **có tham số `?`** (chống SQL injection).

**Đăng nhập & phân quyền:**
- `POST /api/login`: kiểm tra mật khẩu bằng `check_password_hash` (PBKDF2), cấp **token ngẫu nhiên** (`secrets.token_urlsafe`), hiệu lực 8 giờ, lưu trong bộ nhớ `SESSIONS`.
- **Chống dò mật khẩu:** sai 5 lần → khóa IP đó 5 phút (HTTP 429).
- Decorator `require_auth(["Admin"])`: thiếu/hết hạn token → 401; sai vai trò → 403. Frontend gửi token qua header `Authorization: Bearer ...`.

**Các nhóm API:**

| Nhóm | Endpoint | Quyền | Ghi chú |
|---|---|---|---|
| Công khai | `GET /api/public-stats` | không cần | chỉ số tổng cho trang đăng nhập |
| Tài khoản | `POST /api/login`, `GET /api/me`, `POST /api/logout`, `GET /api/permissions` | đăng nhập | |
| Sản phẩm | `GET /api/products`, `GET /api/products/<id>`, `GET .../history`, `GET /api/lookups` | đăng nhập | |
| CRUD | `POST /api/products`, `PUT /api/products/<id>`, `DELETE /api/products/<id>` | Admin | `validate_product` kiểm tra dữ liệu |
| Thống kê | `GET /api/price-statistics`, `/api/price-trend`, `/api/data-quality` | đăng nhập | |
| Review | `GET /api/reviews` (`?product_id=`, `?fields=stats`), `GET /api/reviews/counts` | đăng nhập | tải theo sản phẩm, không tải toàn bộ |
| Thu thập | `GET /api/crawl`, `POST /api/crawl/start`, `POST /api/crawl/stop`, `PUT /api/crawl/schedule` | Admin | |
| Sao lưu | `GET/POST /api/backups`, `POST /api/backups/upload`, `POST /api/backups/<tên>/restore`, `GET .../download` | Admin | |
| Học máy | `GET /api/predictions`, `/api/clusters`, `/api/clusters/summary`, `/api/clusters/features`, `/api/anomalies` | đăng nhập | đọc bảng `ml_*` |

**Chi tiết đáng nhớ:**
- **Sửa giá không ghi đè:** `update_product` thêm snapshot mới (`insert_snapshot`) → lịch sử giá giữ nguyên. `validate_product` từ chối giá ≤ 0, niêm yết < giá bán, link không phải http(s) (chống `javascript:`), nhà bán lẻ/danh mục không tồn tại.
- **Thu thập chạy nền:** lớp `CrawlJob` chạy `crawl.run()` trong 1 thread, giữ 400 dòng nhật ký để trang web hỏi lại mỗi 2 giây; chỉ 1 job cùng lúc (job thứ hai → 409); nút Dừng đặt `stop` event.
  `clean_crawl_options` kiểm tra tùy chọn (giới hạn số trang, giãn cách ≥ 1 giây…).
- **Lịch tự động:** cấu hình lưu trong `app_settings`; `scheduler_loop` kiểm tra mỗi 30 giây, đến giờ thì tự chạy job. Chỉ chạy khi server đang mở.
- **Sao lưu:** `create_backup` dùng **SQLite Online Backup API** (an toàn khi web đang chạy), rồi kiểm tra ngay `integrity_check` + đếm 13 bảng + **mã băm SHA-256**.
- **Phục hồi có kiểm chứng:** `restore_backup` đối chiếu SHA-256 (tệp bị sửa → từ chối), **tự sao lưu dữ liệu hiện tại trước** (đuôi `_truoc-phuc-hoi`), phục hồi, rồi so số dòng 13 bảng → trả "khớp 100%" hoặc chỉ ra bảng lệch.
- **Tải lên bản sao lưu:** `check_uploaded_db` chỉ nhận tệp đúng định dạng SQLite, đủ bảng và cột, **không có view/trigger lạ** (có thể chạy lệnh ngầm), có tài khoản Admin, qua integrity_check. Tải lên chỉ thêm vào danh sách; phục hồi vẫn đi qua quy trình trên.
- **Phục vụ frontend:** `/<path>` chỉ trả file có đuôi cho phép (`.html .css .js …`); gọi API không tồn tại → 404 mã `API_NOT_FOUND` kèm hướng dẫn khởi động lại server.
- **Xử lý lỗi tập trung:** lỗi HTTP, lỗi ràng buộc CSDL và lỗi không lường trước đều trả JSON thống nhất `{status: "error", message}`; lỗi 500 không lộ chi tiết ra ngoài (chỉ ghi log).
- **Khởi động:** nếu cổng đã có server khác (thường là cửa sổ cũ chưa tắt) thì dừng và hướng dẫn, tránh 2 server chạy lẫn nhau.

### 5.2 Frontend (`source-code/frontend/`)

**`common.js` – thư viện dùng chung (đối tượng `BP`):**
- `BP.api(path, {method, body})`: gọi API, tự gắn token, hết phiên (401) → về trang đăng nhập, lỗi → thông báo dễ hiểu.
- Phiên đăng nhập lưu trong `sessionStorage`; `BP.isAdmin()` để ẩn/hiện chức năng theo vai trò (backend vẫn kiểm tra lại quyền – giao diện chỉ là lớp thứ hai).
- Dựng sidebar/menu theo vai trò, định dạng số/tiền/ngày kiểu Việt Nam, `BP.escapeHtml` (chống XSS khi chèn dữ liệu vào HTML), bộ icon SVG, `BP.chart` (bọc Chart.js với bảng màu đã kiểm tra cho người mù màu), xuất CSV có BOM để Excel đọc đúng tiếng Việt.

| Trang | File | Chức năng chính |
|---|---|---|
| Đăng nhập | `login.*` | form + tài khoản demo; số liệu thật từ `/api/public-stats` |
| Tổng quan | `dashboard.html` + `script.js` | KPI, bộ lọc, 6 biểu đồ, nhận định tự động |
| Tra cứu | `tracuu.*` | tìm không dấu, lọc, sắp xếp, phân trang, **CRUD** (Admin), lịch sử giá, review (có tên rút gọn), xuất CSV |
| Phân khúc | `phankhuc.*` | chọn k theo silhouette, đặc điểm cụm, sản phẩm theo cụm |
| Dự đoán giá | `dudoan.*` | so sánh mô hình, ma trận nhầm lẫn, độ quan trọng đặc trưng, bảng dự đoán |
| Bất thường | `batthuong.*` | danh sách bất thường + lý do, độ nhạy contamination |
| Báo cáo | `baocao.*` | thống kê mô tả, min–max, review, quy trình làm sạch (`etl_log`), in PDF, xuất CSV |
| Thu thập | `thuthap.*` | chọn nguồn/danh mục/lượng dữ liệu, chạy nền + nhật ký, lịch tự động, lịch sử (Admin) |
| Sao lưu | `saoluu.*` | tạo/tải về/tải lên/phục hồi + bảng kiểm tra sau phục hồi (Admin) |

`style.css` là hệ thống thiết kế chung (màu, bo góc, thẻ, nút, bảng, modal, responsive cho điện thoại, chế độ in).

---

## Phần 6. Kiểm thử

| File | Kiểm tra gì |
|---|---|
| `tests/test_api.py` | đăng nhập, 401/403, kiểm tra dữ liệu vào, CRUD giữ lịch sử giá, review theo sản phẩm, tùy chọn/lịch thu thập |
| `tests/test_backup.py` | **phục hồi thật**: sao lưu → xóa/sửa dữ liệu → phục hồi → so khớp từng bảng; tệp bị sửa bị từ chối; tải lên tệp hợp lệ/không hợp lệ (7 trường hợp xấu) |
| `tests/test_crawler.py` | công thức mã sản phẩm khớp dữ liệu gốc, đọc HTML Guardian, nạp review + nối biến thể, review Cocolux, rút gọn tên (không cần mạng) |
| `tests/e2e/testcases.js` | 21 test case chạy trên trình duyệt thật (Puppeteer), chụp màn hình → `reports/TEST_CASES.md` |

Mọi test chạy trên **bản sao** CSDL trong thư mục tạm, không đụng `dataset/beautyprice.db`.

---

## Phần 7. Câu hỏi vấn đáp thường gặp

**Dữ liệu**
1. *Tổng bao nhiêu sản phẩm? Sao có số 6.350?* → 5.657 sản phẩm; 6.350 là số bản ghi giá vì sản phẩm thuộc nhiều danh mục được ghi lại theo từng danh mục (xem 1.4).
2. *Làm sạch những gì?* → chuẩn hóa văn bản/Unicode, gộp thương hiệu, loại trùng, loại giá ≤ 0, bỏ giá niêm yết vô lý, tính lại % giảm, rating 0 → NULL, chuẩn hóa ngày; mỗi bước ghi `etl_log` và hiện ở trang Báo cáo.
3. *Thiếu dữ liệu xử lý sao?* → để NULL, không tự đoán; mô hình dùng `SimpleImputer` trong pipeline học máy (học từ tập train).
4. *Làm sao biết CSDL nạp đúng?* → `verify_database.py` tính lại độc lập từ CSV bằng Python và so với SQL; tất cả PASS (`reports/KIEM_TRA_CSDL.md`).

**CSDL**
5. *Vì sao SQLite mà không MongoDB/MySQL?* → không cần cài máy chủ, 1 file mang đi được, có SQL đầy đủ (khóa ngoại, view, window function); dữ liệu có quan hệ rõ (sản phẩm – giá – review). `queries.sql` ghi câu MongoDB tương đương để đối chiếu.
6. *Lấy giá mới nhất thế nào?* → view `v_latest_snapshot` dùng `ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY collected_at DESC)`, lấy dòng số 1.
7. *Chống SQL injection?* → mọi câu SQL dùng tham số `?`, không ghép chuỗi giá trị người dùng.

**Học máy**
8. *Chọn mô hình thế nào, có gian lận dữ liệu test không?* → chia 60/20/20, chọn trên validation, test chỉ để báo cáo mô hình đã chọn; ngưỡng phân khúc tính trên train.
9. *Vì sao dự đoán log(giá)?* → phân bố giá lệch phải; log làm sai số tương đối đều hơn, mô hình ổn định hơn.
10. *R² 0,54 có thấp không?* → giải thích ~một nửa biến động; thiếu thông tin thành phần/xuất xứ/hình ảnh; vẫn tốt hơn hẳn Dummy.
11. *K-Means chọn k bằng gì? Silhouette là gì?* → thử k = 2…10, chọn silhouette cao nhất (đo độ "gần cụm mình, xa cụm khác", từ −1 đến 1).
12. *Isolation Forest hoạt động thế nào?* → cô lập điểm bằng cây cắt ngẫu nhiên; điểm bất thường bị cô lập sau ít lần cắt → điểm số thấp; contamination 5% = tỷ lệ dự kiến bất thường.

**Thu thập**
13. *Thu thập có hợp pháp/đạo đức không?* → chỉ dùng API/trang công khai, tôn trọng robots.txt, giãn cách ≥ 1 giây, ghi rõ User-Agent, không vượt chống bot, tên người đánh giá chỉ lưu dạng rút gọn.
14. *Thu thập lại có làm trùng dữ liệu không?* → không: mã sản phẩm và mã snapshot là hàm băm cố định; review chống trùng theo (nguồn, review_id); mặc định không thêm sản phẩm mới.
15. *Vì sao một số sản phẩm không có review?* → hoặc website không có đánh giá, hoặc nguồn chặn bot (Guardian/Watsons), hoặc chưa thu thập; trang Tra cứu ghi rõ lý do từng trường hợp.

**Website & bảo mật**
16. *Phân quyền thế nào?* → 2 vai trò Admin/User; backend kiểm tra bằng decorator `require_auth` (401 chưa đăng nhập, 403 sai quyền); giao diện ẩn nút chỉ để tiện dùng.
17. *Mật khẩu lưu thế nào?* → băm PBKDF2-SHA256 có salt (werkzeug), không lưu mật khẩu gốc; sai 5 lần khóa 5 phút.
18. *Chống XSS?* → dữ liệu chèn vào HTML đều qua `escapeHtml`; link sản phẩm chỉ nhận http(s).
19. *Sao lưu/phục hồi chứng minh thế nào là đúng?* → sau phục hồi kiểm tra toàn vẹn, khóa ngoại và so số dòng 13 bảng với bản sao lưu; có test tự động xóa/sửa dữ liệu rồi phục hồi và so khớp.

**Vận hành**
20. *Trang báo "Máy chủ đang chạy chưa có chức năng này"?* → server cũ còn chạy: chạy `restart.bat` (hoặc `stop.bat` rồi `run.bat`).

---

## Phần 8. Hạn chế và hướng phát triển (nên chủ động nói khi được hỏi)

- Phiên đăng nhập lưu trong bộ nhớ → khởi động lại server phải đăng nhập lại; hướng phát triển: lưu phiên trong CSDL hoặc dùng JWT.
- Lịch thu thập chỉ chạy khi server mở; triển khai thật nên dùng Task Scheduler/cron.
- Guardian/Watsons chặn bot → chỉ có dữ liệu gốc; hướng phát triển: xin phép/API đối tác, hoặc thay bằng nhà bán lẻ cho phép (đã kiểm tra Lam Thảo Cosmetics và Mint07 có API công khai).
- Mô hình giá thiếu đặc trưng về thành phần, xuất xứ, hình ảnh → R² còn hạn chế.
- Đối chiếu cùng một sản phẩm giữa các nhà bán lẻ (`product_matching`) mới ở mức ứng viên, chưa dùng để so giá chéo.
