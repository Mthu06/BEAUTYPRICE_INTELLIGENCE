# Báo cáo rà soát và nâng cấp — BeautyPrice Intelligence

Cập nhật: 29/10/2026
Phạm vi: toàn bộ dự án (backend Flask, frontend, dữ liệu, mô hình, script phân tích)

Tài liệu gồm:
1. Cách chạy dự án.
2. Đợt 1: các lỗi và lỗ hổng đã tìm thấy và đã sửa.
3. Đợt 2: nâng cấp để đạt yêu cầu đồ án (SQLite, làm sạch, học máy, giao diện).
4. Những điểm còn tồn tại, cần nhóm quyết định.
5. Các kiểm thử đã chạy.
6. Giai đoạn 8: website GUI và chức năng cộng điểm.
7. Đợt 3: thu thập trên website, review, sao lưu tải lên, giao diện mới (các lỗi tìm thấy và đã sửa).

---

## 1. Cách chạy

Xem [README.md](../README.md). Tóm tắt:
- Cài Python 3.9+, rồi nháy đúp `run.bat` (Windows) hoặc chạy `./run.sh` (macOS/Linux). `run.*` tự tắt server cũ trước khi chạy.
- Mở `http://127.0.0.1:5000/`, đăng nhập bằng `admin / Admin@123` hoặc `user / User@123`.
- Tắt server: `stop.bat` / `./stop.sh`. Sau khi cập nhật code: `restart.bat` / `./restart.sh`.

Không cần MySQL: CSDL là SQLite (`dataset/beautyprice.db`). Nếu chưa có file này, backend tự dựng lại từ `dataset/raw`.

> Ở mục 2, đường dẫn như `backend/app.py`, `frontend/...`, `gđ6cc/...` là **cấu trúc cũ**. Sau đợt 2, các file này nằm lần lượt ở `source-code/backend/`, `source-code/frontend/`, `source-code/analysis/` và `dataset/raw/`. Một số chi tiết đợt 1 (file `products_working.json`, `/api/price-statistics` đọc JSON...) đã được thay thế bằng CSDL ở đợt 2.

---

## 2. Đợt 1: lỗi và lỗ hổng đã tìm thấy và đã sửa

Mức độ: 🔴 Nghiêm trọng · 🟠 Cao · 🟡 Trung bình · ⚪ Thấp

### 2.1. Bảo mật và phân quyền

| # | Mức | Lỗi | Hậu quả | Đã sửa |
|---|---|---|---|---|
| S1 | 🔴 | Đăng nhập chỉ kiểm tra trong `login.js`: mật khẩu `admin123` nằm ngay trong JS, kết quả chỉ lưu thành cờ `beautyprice_logged_in` trong sessionStorage. Frontend không bao giờ gọi `/api/login`. | Ai cũng đọc được mật khẩu. Gõ `sessionStorage.setItem("beautyprice_role","admin")` trong DevTools là "thành admin". | Đăng nhập qua `POST /api/login` và nhận token. `common.js` gửi `Authorization: Bearer` và xác minh lại bằng `/api/me`. Vai trò lấy từ server: thử giả mạo role trên trình duyệt thì vẫn bị trả về USER. |
| S2 | 🔴 | Các API dữ liệu (`/api/products`, `/reviews`, `/predictions`, `/clusters`...) không yêu cầu đăng nhập. | Màn hình đăng nhập chỉ mang tính hình thức; ai gọi API trực tiếp cũng lấy được toàn bộ dữ liệu. | Thêm `@require_auth()` cho mọi API dữ liệu. |
| S3 | 🟠 | Mật khẩu frontend (`admin123`) khác backend (`Admin@123`). Các nút thêm/sửa/xóa không gửi token. | Admin **không bao giờ** thêm/sửa/xóa được (luôn lỗi 401). | Đã thống nhất. CRUD hoạt động; tài khoản user gọi CRUD nhận 403. |
| S4 | 🟠 | Phiên đăng nhập không có hạn; không giới hạn số lần đăng nhập sai. | Token dùng mãi mãi; có thể dò mật khẩu không giới hạn. | Phiên hết hạn sau 8 giờ (cấu hình được). Sai 5 lần thì khóa 5 phút (HTTP 429). |
| S5 | 🟠 | `hmac.compare_digest(password, ...)` dùng trên chuỗi. | Mật khẩu có dấu tiếng Việt làm server **crash (500)**. | Dùng `werkzeug.security` (băm PBKDF2). Mật khẩu chỉ lưu dạng băm. |
| S6 | 🟠 | `app.run(debug=True)` | Trình debug Werkzeug cho phép chạy mã tùy ý nếu server bị lộ ra mạng. | Debug tắt mặc định; chỉ bật khi đặt `FLASK_DEBUG=1`. |
| S7 | 🟡 | `product_url` không được kiểm tra; trang tra cứu chèn thẳng vào `href`. | Có thể lưu link `javascript:...` và bấm vào sẽ chạy mã (XSS). | Backend chỉ nhận link `http(s)`. Frontend lọc thêm bằng `BP.safeUrl` và gắn `rel="noopener noreferrer"`. |
| S8 | 🟡 | Body JSON không phải object (ví dụ `[1,2]`) làm `data.get` lỗi. | Lỗi 500. | `json_body()` chỉ nhận object. Có trình xử lý lỗi chung trả JSON và không lộ chi tiết lỗi. |
| S9 | ⚪ | Một số chỗ dùng `innerHTML` mà chưa escape (ví dụ nhóm giá ở trang dự đoán). | Có thể bị XSS nếu dữ liệu chứa HTML. | Mọi chuỗi chèn vào HTML đều đi qua `BP.escapeHtml`. |
| S10 | ⚪ | File xuất CSV không chống chèn công thức. | Tên thương hiệu dạng `=HYPERLINK(...)` sẽ chạy khi mở file bằng Excel. | Thêm `'` trước các ô bắt đầu bằng `= + - @`. |

### 2.2. Sai nghiệp vụ và số liệu

| # | Mức | Lỗi | Hậu quả | Đã sửa |
|---|---|---|---|---|
| D1 | 🔴 | Mỗi lần đọc dữ liệu, hàm `repair_working_product_discounts` **ghi đè giá và giảm giá** bằng số trong CSV. | Admin sửa giá xong, lần tải sau giá **tự quay về giá cũ**. Chức năng sửa coi như vô dụng. | Bỏ hàm này. Chỉ còn một bước nâng cấp file cũ: bổ sung trường còn thiếu, không ghi đè. Đã kiểm thử: chỉnh sửa vẫn còn sau khi tải lại. |
| D2 | 🟠 | Review Guardian có điểm nửa sao (4.5, 3.5, 2.5) nhưng bị ép sang số nguyên (`to_int`). | 4.5 bị cắt thành 4, 2.5 thành 2, nên điểm trung bình bị kéo xuống. | Giữ số thực, làm tròn 1 chữ số; hợp lệ trong khoảng 1–5. |
| D3 | 🟠 | Review được gắn vào sản phẩm theo **tên gần đúng** (`includes`). | Gắn nhầm review: combo "nuốt" review của sản phẩm lẻ, review lẫn giữa các nhà bán lẻ. Chỉ 1.000/2.751 sản phẩm có review. Mỗi lần vẽ bảng mất khoảng 1,8 giây. | Nối theo **ID nguồn** (`review_key`). Hasaki dùng số ID ở cuối URL (= `source_product_id`); Guardian dùng URL đã chuẩn hóa. Kết quả: khớp 6.178/6.263 review Hasaki và 410/410 review Guardian; mỗi lần vẽ bảng còn khoảng 4 ms. |
| D4 | 🟠 | `rating` và `review_count` có trong `price_snapshots.csv` nhưng backend bỏ đi; trang phân cụm gán **rating = 5.0 cho mọi sản phẩm**. | Thẻ cụm nào cũng ghi "rating trung vị 5.0"; nhận định "cụm có rating cao nhất" là sai. | Lấy rating thật (2.817 sản phẩm có rating). Thẻ cụm lấy từ `kmeans_cluster_summary.csv` chính thức; thiếu dữ liệu thì ghi "Chưa có dữ liệu". |
| D5 | 🟠 | Sản phẩm chưa được phân cụm thì bị **tự gán cụm 0/1/2 theo giá**. | Sản phẩm admin thêm mới bị xếp vào cụm K-Means mang ý nghĩa khác hẳn. | Trả về `cluster: null` và hiển thị "Chưa phân cụm". |
| D6 | 🟠 | Trang Báo cáo đọc `review.purchased` trong khi trường đúng là `is_bought`. | Tỷ lệ "Đã mua" **luôn 0%** (thực tế là 74,5%). | Đọc đúng `is_bought` / `has_images`; mẫu số chỉ gồm review có thông tin. |
| D7 | 🟡 | Giá trung bình ở Dashboard và Báo cáo lấy từ 6.350 snapshot, còn bảng và biểu đồ lấy từ 5.657 sản phẩm. | Số liệu trên cùng một trang không khớp; bộ lọc không làm đổi giá trung bình; số liệu không cập nhật sau thêm/sửa/xóa. | Mọi KPI tính từ danh sách sản phẩm hiện tại (đã lọc). `/api/price-statistics` cũng tính trên sản phẩm hiện tại. |
| D8 | 🟡 | Khoảng lọc giảm giá có "lỗ hổng": 0–1%, 10–11%, 20–21% không thuộc nhóm nào. | 224 sản phẩm (ví dụ giảm 10,05%) không bao giờ tìm thấy được qua bộ lọc giảm giá. | Dùng chung `BP.discountBucket` (khoảng nửa mở `(0,10]`, `(10,20]`...); nhãn ghi lại cho đúng. |
| D9 | 🟡 | Ranh giới 500.000đ: Dashboard dùng `<=`, Báo cáo dùng `<`. | 9 sản phẩm giá đúng 500.000đ nằm ở hai nhóm khác nhau trên hai trang. | Thống nhất khoảng nửa mở `[min, max)`. |
| D10 | 🟡 | Form sửa cho nhập giảm giá tùy ý, không kiểm tra giá niêm yết ≥ giá bán; lệnh PUT cho phép giá ≤ 0. | Dữ liệu mâu thuẫn (ví dụ niêm yết 100k, bán 90k, giảm 50%). | Backend kiểm tra mọi ràng buộc. Giảm giá được **tự tính** = (niêm yết − bán) / niêm yết × 100, đúng quy tắc trong README Giai đoạn 6. |
| D11 | 🟡 | Ô giảm giá đặt `step="0.1"` trong khi dữ liệu có 2 chữ số thập phân. | **42% sản phẩm (2.390) không lưu được form sửa** vì trình duyệt chặn. | Ô giảm giá giờ chỉ đọc, tự tính từ hai ô giá; ô giá dùng `step="any"`. |
| D12 | 🟡 | Chỉ số MAE/RMSE/R² ghi cứng trong code (cả backend và frontend). Trang dự đoán có số giả "338". | Chạy lại mô hình xong, trang vẫn hiện số cũ như thể số thật. | Đọc từ `ML/regression_final_test_metrics.csv`; thiếu số thì hiện "—". |
| D13 | 🟡 | Nhận định "nhóm có MAE thấp nhất" so sai số tuyệt đối (VNĐ) giữa các nhóm giá. | Nhóm giá rẻ luôn "thắng", trong khi sai số tương đối của nhóm này tệ nhất (MAPE 80%). | So sánh theo MAPE trong từng nhóm giá thực tế (ngưỡng q1/q2 lấy từ API). |
| D14 | ⚪ | Danh mục trống bị hiển thị thành "Mỹ phẩm & Chăm sóc da" (nhãn tự đặt). | Dữ liệu bị bịa thêm. | Hiển thị "Không rõ". |
| D15 | ⚪ | Ngày review Guardian ("22 tháng 4, 2025") qua `new Date()` thành NaN. | Sắp xếp "mới nhất / cũ nhất" không có tác dụng. | Dùng `BP.parseReviewDate` hiểu được cả hai định dạng. |
| D16 | ⚪ | Tìm kiếm phân biệt dấu; 6 tên sản phẩm chứa ký tự vô hình (zero-width). | Gõ "sua rua mat" không ra "Sữa rửa mặt". | Tìm kiếm không phân biệt dấu, bỏ ký tự vô hình, có debounce. |

### 2.3. Lỗi kỹ thuật backend

| # | Mức | Lỗi | Đã sửa |
|---|---|---|---|
| B1 | 🟠 | Thêm/sửa/xóa theo kiểu đọc → sửa → ghi file mà không có khóa, trong khi server chạy đa luồng. Hai yêu cầu cùng lúc làm mất dữ liệu. | Thêm lớp `ProductStore` có `RLock`; ghi file nguyên tử (`.tmp` rồi `os.replace`); nếu ghi lỗi thì khôi phục bản trong RAM. |
| B2 | 🟡 | Mỗi request đều đọc lại toàn bộ CSV và JSON (6.350 dòng giá, 6.673 review). Một request GET còn có thể ghi file. | Có bộ đệm theo thời điểm sửa file (mtime), chỉ đọc lại khi file đổi. GET không còn ghi file. Lần gọi `/api/products` thứ hai mất khoảng 0,05 giây. |
| B3 | 🟡 | `GD6CC_DIR = "extracted_gđ6cc"` không tồn tại. Hàm tìm review quét đệ quy **toàn bộ dự án** và đọc nhầm `ML/product_matching_review.csv` cùng các bản sao trong `gđ6cc/`. | Đường dẫn dữ liệu rõ ràng trong `backend/`, có thể đổi bằng `BEAUTY_DATA_DIR`. |
| B4 | 🟡 | `print()` tiếng Việt trên console Windows (cp1252, hoặc khi chuyển hướng ra file) gây `UnicodeEncodeError` và làm crash. | Chuyển stdout/stderr sang UTF-8 khi khởi động. |
| B5 | ⚪ | Không có `requirements.txt`. `__pycache__` của Python 3.15 bị đóng gói kèm. | Thêm `backend/requirements.txt` và `.gitignore`; xóa `__pycache__`. |
| B6 | ⚪ | Code 3.065 dòng do mỗi đối số xuống một dòng; nhiều hàm chuyển số trùng nhau (`to_float`, `to_price_float`, `to_ml_float`...). | Viết lại còn 777 dòng; một hàm `to_number` duy nhất. API giữ nguyên tên trường để tương thích. |

### 2.4. Lỗi frontend

| # | Mức | Trang | Lỗi | Đã sửa |
|---|---|---|---|---|
| F1 | 🟠 | Tất cả | API ghi cứng `http://127.0.0.1:5000`; CORS chỉ cho cổng 5500. Mở bằng `file://`, cổng khác hoặc từ máy khác trong mạng LAN đều lỗi. | `common.js` tự xác định địa chỉ API; backend phục vụ luôn frontend (cùng origin). |
| F2 | 🟠 | Phân khúc | Chart.js tải từ CDN không cố định phiên bản. Khi CDN đổi bản lớn hoặc mất mạng, **cả trang** báo lỗi "kiểm tra backend". | Cố định `chart.js@4.4.1`. Biểu đồ nằm trong try/catch riêng nên lỗi biểu đồ không làm hỏng phần còn lại. |
| F3 | 🟡 | Tất cả | Mỗi trang tự chép lại đoạn kiểm tra đăng nhập (chạy sau khi trang đã hiện ra, nên trang nháy). Nút Đăng xuất không gọi `/api/logout`. | Gộp vào `common.js`, chạy ngay trong `<head>` trước khi trang hiện. Đăng xuất hủy token trên server. |
| F4 | 🟡 | Tra cứu | Sau khi sửa hoặc xóa thì nhảy về trang 1. Bộ lọc review không reset khi mở sản phẩm khác. Modal đóng khi đang lưu. | Giữ trang hiện tại; reset bộ lọc khi đổi sản phẩm; không cho đóng modal khi đang gửi yêu cầu. |
| F5 | 🟡 | Dashboard, Báo cáo, Phân khúc | Khi lỗi tải dữ liệu, chữ "Đang tải dữ liệu..." treo mãi; ô tổng review hiện "0". | Hiện thông báo lỗi thật từ server; số thiếu hiện "—". |
| F6 | 🟡 | Dự đoán | Vẽ một lần cả 1.132 dòng. Bộ lọc không hoạt động nếu lần tải đầu lỗi. | Phân trang 100 dòng mỗi trang; gắn sự kiện lọc ngay từ đầu. |
| F7 | ⚪ | Tất cả | Dữ liệu thiếu bị biến thành `0đ` hoặc `NaN`. | `BP.toNumber` trả `null`; hiển thị "—". |
| F8 | ⚪ | Báo cáo | Không tự cập nhật khi tab khác thêm/sửa/xóa. CSS khi in trỏ tới class không tồn tại. | Lắng nghe `BP.onProductsUpdated`; sửa CSS in. |
| F9 | ⚪ | Dashboard | Thiếu thẻ `</head>`; nút "•••" không có chức năng; code chết. | Đã dọn. |
| F10 | ⚪ | — | `dashboard(demo).html`, `script (demo).js`, `hasaki_products_pages_1_9.csv` không được trang nào dùng (file demo lại tham chiếu `auth.js` không tồn tại). | Đã xóa. |

### 2.5. Giai đoạn 6 (`gđ6cc/kqptr - Sao chép/`)

| # | Mức | Lỗi | Đã sửa |
|---|---|---|---|
| G1 | 🟡 | `05_validate_stage6.py` ghi cứng đường dẫn Node.js vào `~/.cache/codex-runtimes/...` (thư mục của một công cụ AI trên máy người viết). Sang máy khác, bước kiểm tra JS luôn thất bại. | Ưu tiên `shutil.which("node")`, giống `02_ve_bieu_do.py`. |
| G2 | ⚪ | README nhắc thư mục `BDr/datar` không tồn tại (thực tế là `gđ6cc/datar`). Script dùng `rglob` nên vẫn chạy được. | Chưa sửa; ghi chú lại ở đây. |

---

## 3. Đợt 2: nâng cấp để đạt yêu cầu đồ án

Căn cứ đối chiếu là file hướng dẫn đồ án *LabF_CourseProject (ABDA433708)*.

### 3.1. Đối chiếu với yêu cầu

| Mục | Yêu cầu | Trước đợt 2 | Sau đợt 2 |
|---|---|---|---|
| 2.1 | Phân tích đối tượng, thuộc tính, ràng buộc, quan hệ | Chỉ có các file CSV | ✅ ERD và từ điển dữ liệu: `reports/THIET_KE_CSDL.md` |
| 2.1 | Thiết kế mô hình quan hệ | Không có | ✅ `source-code/pipeline/schema.sql`: 17 bảng, 2 view, khóa ngoại, CHECK, UNIQUE, chỉ mục |
| 2.1 | **Chọn hệ quản trị CSDL** | ❌ Lưu bằng CSV/JSON | ✅ **SQLite** (`dataset/beautyprice.db`), không cần cài đặt |
| 2.1 | Công cụ thu thập đa nguồn (điểm cộng) | Không có code | ✅ `source-code/crawler/crawl.py` + trang **Thu thập dữ liệu** (chạy nền, lịch tự động): giá 3 nguồn đang lấy được (Hasaki, Cocolux, Thế Giới Skin Food), review Hasaki + Cocolux; Guardian, Watsons bật chống bot nên chỉ ghi nhận `blocked` (xem 3.5, mục 7) |
| 2.2 | **Chương trình làm sạch** | ❌ Không có | ✅ `build_database.py`: 24 bước, mỗi bước ghi vào `etl_log`, hiển thị ở trang Báo cáo |
| 2.3 | Danh sách thống kê, min – max | Một phần | ✅ Trang Báo cáo: min–max theo danh mục, theo nhà bán lẻ, theo chỉ số |
| 2.3 | Biểu đồ đa dạng | Chỉ có biểu đồ cột | ✅ 20 biểu đồ: cột, cột ngang, cột chồng 100%, doughnut, đường, scatter, bubble, heatmap (ma trận nhầm lẫn) |
| 2.4 | Học không giám sát | K-Means (chỉ có kết quả) | ✅ K-Means, chọn k theo silhouette, **có code huấn luyện** |
| 2.4 | Học giám sát | Random Forest (chỉ có kết quả) | ✅ Hồi quy giá (4 mô hình) và phân loại phân khúc (4 mô hình), **có code** |
| 2.4 | **Phát hiện bất thường** | ❌ Có kết quả nhưng không có trên web | ✅ Isolation Forest, **trang mới** "Phát hiện bất thường" |
| 2.4 | Phân quyền theo đăng nhập | Đã sửa ở đợt 1 | ✅ Người dùng lưu trong CSDL, mật khẩu băm PBKDF2 |
| 2.4 | Tìm kiếm, lọc (điểm cộng) | ✅ | ✅ |
| 2.4 | CRUD (điểm cộng) | ✅ (ghi file JSON) | ✅ Ghi CSDL. **Đổi giá thì thêm snapshot**, nên giữ được lịch sử giá |
| 2.4 | Kết xuất báo cáo ra file (điểm cộng) | CSV | ✅ CSV ở 4 trang (Tra cứu, Dự đoán, Bất thường, Báo cáo) và In / Lưu PDF ở trang Báo cáo |
| 2.5 | Nhận định về dữ liệu | ✅ | ✅ Nhận định tự sinh trên 6 trang và `source-code/analysis/03_insight.md` |
| 1, 5 | Cấu trúc thư mục nộp bài, `readme.txt` | ❌ | ✅ `source-code/`, `dataset/`, `reports/`, `refs/`, `libs/`, `readme.txt` |
| 1, 3 | **Git, tracking đóng góp** | ❌ | ⚠️ **Nhóm tự làm**: mỗi thành viên commit phần mình phụ trách |
| 2.5 | Quyển báo cáo, slides, bảng phân công | — | ⚠️ Nhóm tự làm, đặt vào `reports/` |

### 3.2. Cơ sở dữ liệu SQLite
- **Lược đồ** (`schema.sql`):
  - Bảng: `retailers`, `categories`, `products`, `product_categories` (quan hệ N-N), `price_snapshots`, `reviews`, `review_links` (review dùng chung giữa biến thể), `users`, `app_settings` (lịch thu thập), `collection_logs`, `product_matching`, `etl_log`, cùng 5 bảng `ml_*`.
  - View: `v_latest_snapshot` (giá hiện tại) và `v_products`.
- **Sửa một lỗi nghiệp vụ:** trước đây khi admin sửa giá, file JSON bị ghi đè nên **mất lịch sử giá**. Giờ mỗi lần đổi giá thêm một dòng `price_snapshots`, và trang Tra cứu có biểu đồ lịch sử giá.
- **Tự dựng CSDL:** chưa có `beautyprice.db` thì backend tự chạy `build_database.py`. Đã thử trên một bản sao dự án không có CSDL.

### 3.3. Chương trình làm sạch: `build_database.py`
Chỉ dùng thư viện chuẩn của Python. Kết quả trên dữ liệu hiện tại:

| Bước | Tác động |
|---|---|
| Chuẩn Unicode, bỏ ký tự vô hình, gộp khoảng trắng trong tên | 43 sản phẩm |
| Gộp thương hiệu viết khác nhau ("LA ROCHE POSAY" / "La Roche-Posay", "L'Oréal" / "L'Oreal") | 1.611 sản phẩm, còn 418 thương hiệu |
| Danh mục không hợp lệ hoặc trống thì ghi NULL | 569 sản phẩm |
| Trích dung tích, khối lượng, số món, combo từ tên | 5.304 sản phẩm có dung tích hoặc khối lượng |
| Tính lại % giảm = (niêm yết − bán) / niêm yết | 4.861 snapshot; 114 dòng lệch so với nguồn quá 1 điểm % |
| Không đủ cặp giá thì để % giảm là NULL (trước đây ghi nhầm thành 0%) | 1.489 snapshot |
| Rating = 0 thì ghi NULL (chưa có đánh giá) | 864 snapshot |
| Chuẩn hóa ngày review về ISO (2 định dạng nguồn) | 6.673 review |
| Nối review với sản phẩm theo ID nguồn | 6.588 / 6.673 review |
| Loại trùng, sai khóa, giá ≤ 0, giá niêm yết nhỏ hơn giá bán | 0 dòng. Dữ liệu nguồn đã sạch ở các mặt này, nhưng các bước kiểm tra vẫn chạy |

### 3.4. Học máy: `train_models.py`
Dữ liệu chia train/validation/test theo tỷ lệ 60/20/20 (random_state = 42). Mô hình được chọn trên tập validation, rồi báo cáo kết quả trên tập test.

| Bài toán | Mô hình chọn | Kết quả test | Bản cũ của nhóm |
|---|---|---|---|
| Hồi quy giá (học trên log giá) | Random Forest | MAE 90.290đ · RMSE 168.259đ · R² 0,536 · MAPE 35,2% | MAE 87.919đ · R² 0,652 |
| Phân loại phân khúc giá | Extra Trees | Accuracy 73,5% · F1-macro 0,732 | 73,9% · 0,734 |
| Phân cụm | K-Means, k = 7 | Silhouette 0,285 | k = 7, silhouette 0,284 |
| Bất thường | Isolation Forest, contamination 5% | 283 sản phẩm (5%) | 283 |

Kết quả trên huấn luyện trên **dữ liệu gốc 5.657 sản phẩm** (nhóm chọn giữ đúng dữ liệu gốc cho EDA, mô hình và báo cáo; xem 3.5). Chi tiết: `reports/KET_QUA_MO_HINH.md`.
R² thấp hơn bản cũ: bản cũ dùng thêm đặc trưng `product_variant` và cách chia dữ liệu khác, nhưng code của bản cũ không còn nên không đối chiếu được. Phân cụm và phát hiện bất thường cho kết quả trùng khớp với bản cũ (k = 7, 283 sản phẩm).

### 3.5. Công cụ thu thập đa nguồn: `crawler/crawl.py`

- **Chỉ dùng thư viện chuẩn của Python.**
- Đọc `robots.txt` (hỗ trợ ký tự đại diện `*`, `$`; luật khớp dài nhất thắng) và **không gửi yêu cầu bị cấm**.
- Giãn cách giữa các yêu cầu tới cùng một website (mặc định 1,5 giây, không cho đặt dưới 1 giây); thử lại có giới hạn khi gặp lỗi 5xx hoặc mất kết nối.
- User-Agent ghi rõ đây là công cụ của đồ án sinh viên.

| Nguồn | Cách lấy dữ liệu | Kết quả lần chạy 29/10/2026 |
|---|---|---|
| Hasaki | API JSON `/mobile/v3/main/products` (website tự dùng) | 8 danh mục, 2.000 bản ghi |
| Cocolux | API JSON `/Ajax/Content/PartialProduct` | 7 danh mục, 620 bản ghi |
| Thế Giới Skin Food | Haravan `/collections/<handle>/products.json` | 7 danh mục, 535 bản ghi |
| Guardian | Phân tích HTML trang danh mục Magento (`?p=N` được robots.txt cho phép) | 7 danh mục, 1.102 bản ghi. **Từ chiều 29/10/2026 Guardian bật Cloudflare** (HTTP 403 "Just a moment…") → các lần sau ghi `blocked` |
| Watsons | Akamai chặn truy cập tự động (HTTP 403) | Ghi `blocked` vào `collection_logs`, **không vượt rào chống bot** |

- **Kết quả lần chạy:** 4.257 bản ghi, gộp lại còn 4.074 sản phẩm (có sản phẩm thuộc nhiều danh mục), chỉ dùng 154 yêu cầu HTTP. Lưu ở `dataset/crawl/crawl_20261029T120321/`.
- **Quyết định giữ dữ liệu gốc:** CSDL mặc định **chỉ gồm dữ liệu gốc** (5.657 sản phẩm, 6.350 snapshot), khớp EDA và báo cáo. Lần chạy trên được giữ để truy vết; có 3 cách dùng:

  | Cách | Sản phẩm | Snapshot giá |
  |---|---:|---:|
  | Mặc định (`build_database.py`) | 5.657 | 6.350 |
  | Nạp lần thu thập, chỉ thêm giá cho sản phẩm đã có (mặc định của crawler) | 5.657 | 9.668 (+3.318) |
  | `build_database.py --with-crawl` (thêm cả sản phẩm mới) | 6.413 | 10.424 |

  Cả 3 cách đều qua `verify_database.py` (PASS).
- **Nối dữ liệu mới với dữ liệu cũ:** mã sản phẩm dùng **đúng công thức của dữ liệu gốc**, `prod_ + sha256("<nhà bán lẻ>|<URL>")[:16]` (đã kiểm chứng bằng test). URL Guardian được bỏ `www.` để khớp dạng cũ.
- **Truy vết:** mỗi lần chạy lưu ở `dataset/crawl/crawl_<thời điểm>/`, gồm dữ liệu thô (`raw/*.gz`), `snapshots.csv` và `collection_log.csv`.
- **Dựng lại CSDL:** `build_database.py --force --with-crawl` nạp lại các lần thu thập này (mặc định chỉ dựng từ `dataset/raw/`).
- **Làm sạch khi thu thập:**
  - Loại bản ghi thiếu tên, link hoặc giá.
  - Bỏ giá niêm yết nhỏ hơn giá bán; tính lại % giảm.
  - Rating = 0 ghi NULL.
  - Gộp sản phẩm xuất hiện ở nhiều danh mục.
  - Quy thương hiệu về cách viết đã có trong CSDL; combo nhiều hãng ghi "Không rõ".
  - Đọc được giá dạng chữ của sản phẩm combo trên Guardian.

### 3.6. Giao diện mới
- Hệ thống thiết kế dùng chung (`style.css`), sidebar do `common.js` tự dựng, responsive tới 390px.
- Bảng màu biểu đồ đã kiểm định cho người mù màu, với màu cố định theo từng thực thể (nhà bán lẻ, phân khúc, cụm).
- Chart.js 4.4.1 lưu cục bộ, chạy được khi không có mạng.
- Các trang:
  - Đăng nhập, Tổng quan, Tra cứu (CRUD, lịch sử giá, review).
  - Phân khúc: danh sách đặc trưng lấy từ mô hình, thay cho danh sách viết cứng bị sai trước đây.
  - Dự đoán: so sánh mô hình, độ quan trọng đặc trưng, ma trận nhầm lẫn.
  - **Phát hiện bất thường** (trang mới).
  - Báo cáo: min–max, chất lượng dữ liệu, in/PDF, CSV.
  - **Thu thập dữ liệu**, **Sao lưu & phục hồi** (Admin; xem mục 6 và 7).
- Đợt 3 đổi sang giao diện mới đồng bộ với trang đăng nhập (xem mục 7).

### 3.7. Số dòng code hiện tại

| Phần | Số dòng |
|---|---:|
| `backend/app.py` | 1.056 |
| `pipeline/` (schema.sql + build_database.py + train_models.py + verify_database.py + queries.sql) | 1.332 |
| `frontend/` JS (common.js + 9 trang) | 3.252 |
| `frontend/` HTML + CSS | 2.002 |
| `crawler/crawl.py` | 902 |
| `tests/` (test_api.py + test_backup.py + test_crawler.py) | 470 |

(Số dòng đo ở cuối đợt 3.)

---

## 4. Còn tồn tại, cần nhóm quyết định

1. **Watsons (Akamai) và Guardian (Cloudflare, từ 29/10/2026) chặn truy cập tự động.** Công cụ chỉ ghi nhận trạng thái `blocked`, không giải captcha hay vượt rào; robots.txt của Guardian còn cấm riêng `/review/`. Dữ liệu của 2 nguồn này là bản thu thập gốc. Hướng mở rộng hợp lệ: xin phép/API đối tác, hoặc thêm nhà bán lẻ cho phép thu thập (đã kiểm tra: Lam Thảo Cosmetics và Mint07 có API công khai, robots.txt cho phép).
2. **Git:** repo `Mthu06/beautyprice-analytics` đã có commit của từng thành viên theo phần phụ trách. Đóng góp đang lệch (phần lớn commit của Mthu06); mỗi thành viên nên nắm chắc phần mình qua `reports/GIAI_THICH_CODE.md`. Email `pdat105206@gmail.com` cần được xác minh trên GitHub để commit hiện tên.
3. **Nên bật lịch thu thập tự động** trên trang Thu thập dữ liệu (ví dụ mỗi ngày) để có thêm lịch sử giá, rồi chạy `train_models.py` để mô hình cập nhật. Cấu trúc website có thể thay đổi; khi đó cần sửa phần đọc dữ liệu của nguồn tương ứng trong `crawl.py`.
4. **Dung lượng:**
   - `refs/_luu_tru/` (khoảng 93 MB) là bản trùng của cấu trúc cũ; **nên xóa trước khi nén nộp**.
   - `refs/ml_ket_qua_goc/` (khoảng 60 MB) chỉ để đối chiếu, cũng có thể bỏ.
   - `dataset/models/` (15 MB) có thể tạo lại bằng `train_models.py`.
5. **100% review Guardian có `is_bought = yes`.** Nhiều khả năng đây là giá trị mặc định của nguồn thu thập, không nên dùng để kết luận.
6. **Triển khai thật:** phiên đăng nhập lưu trong RAM, và server là server phát triển của Flask. Nếu triển khai thật nên dùng `waitress` hoặc `gunicorn` và HTTPS.
7. **Dựng lại CSDL** bằng `build_database.py --force` sẽ mất các thay đổi admin đã nhập; bản cũ được giữ trong file `.bak`.

---

## 5. Kiểm thử đã chạy (đợt 2)

- **`source-code/tests/test_crawler.py`** (8 test ở cuối đợt 3, đều đạt, không cần mạng):
  - Mã sản phẩm khớp dữ liệu gốc.
  - Luật robots.txt (`/*?` cấm, `/*?p=*` cho phép, `/*?p=*&*` cấm).
  - Bộ phân tích HTML Guardian: giá khuyến mãi, giá gốc, giá dạng chữ của combo, rating.
  - Bước làm sạch: gộp danh mục, giá niêm yết sai, bản ghi thiếu giá.
  - Nạp review: nối review dùng chung giữa biến thể, chế độ chỉ bổ sung tên; review Cocolux (phân trang, header, rút gọn tên).
- **Thu thập thật toàn bộ 5 nguồn**, nạp vào bản sao CSDL trước rồi mới nạp CSDL thật; không có lỗi khóa ngoại.
- **Dựng lại CSDL từ đầu** cho ra đúng số liệu như khi nạp trực tiếp: mặc định 5.657 sản phẩm / 6.350 snapshot; `--with-crawl` 6.413 / 10.424.

- **`source-code/tests/test_api.py`** (6 test ở cuối đợt 3, đều đạt):
  - Đăng nhập và phân quyền.
  - Các API đọc dữ liệu.
  - Kiểm tra dữ liệu đầu vào: nhà bán lẻ sai, giá niêm yết nhỏ hơn giá bán, giá ≤ 0, link `javascript:`, tên trống.
  - CRUD: đổi tên không sinh snapshot, đổi giá sinh snapshot, xóa thì xóa luôn các snapshot của sản phẩm.
  - Review theo sản phẩm, số liệu công khai của trang đăng nhập, tùy chọn và lịch thu thập (không gọi mạng thật).
- **`source-code/tests/test_backup.py`** (7 test): phục hồi thật có đối chiếu, tệp bị sửa bị từ chối, tải lên tệp hợp lệ / bản cũ / 7 loại tệp xấu.
- **Chạy như trên máy mới,** trên bản sao dự án **không có CSDL**:
  - `run.bat` tự tạo `.venv`, cài Flask, rồi backend tự dựng CSDL từ `dataset/raw`.
  - Khi chưa huấn luyện, các trang mô hình báo "chưa có kết quả" mà không lỗi.
  - Chạy `train_models.py` xong thì cả 6 trang hiển thị đủ.
- **Chrome headless trên cả 6 trang** ở 1440px và 390px:
  - 20 biểu đồ, không có lỗi JS, không có request lỗi, không có NaN/undefined, không tràn ngang.
  - Nút menu chỉ hiện trên điện thoại.
- **Bảo mật:**
  - Chưa đăng nhập thì bị chuyển về login.
  - Tài khoản user không thấy nút sửa/xóa, và gọi API xóa bị chặn (403).
  - Sửa role trên trình duyệt thì bị trả về đúng role trên server.
  - Đăng xuất và token cũ đều bị chuyển về login.
- **Script Giai đoạn 6** (`01_eda.py`, `02_kpi.py`) vẫn chạy được với đường dẫn mới `dataset/raw`.

---

## 6. Giai đoạn 8: Website GUI và chức năng cộng điểm

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Sơ đồ màn hình và luồng người dùng | ✅ | `reports/SO_DO_MAN_HINH.md`: sơ đồ 9 màn hình, ma trận phân quyền, luồng người dùng, wireframe |
| Tích hợp dashboard, dữ liệu, kết quả mô hình | ✅ | Tổng quan, Phân khúc, Dự đoán, Bất thường (TC04, TC12–TC14) |
| Đăng nhập, phân quyền | ✅ | Admin / User, backend chặn 403 (TC01–TC03, TC18–TC20) |
| Tìm kiếm, lọc; CRUD; xuất báo cáo | ✅ | TC05–TC11, TC15; tệp xuất ở `reports/demo/exports/` |
| Backup/restore **có kiểm tra phục hồi thực tế** | ✅ | Trang Sao lưu & phục hồi; `test_backup.py`; TC16–TC17; `reports/demo/backup_evidence/` |
| Test case, ảnh, video demo | ✅ | `reports/TEST_CASES.md` (21/21 PASS), `reports/demo/screens/`, `reports/demo/demo.mp4` |
| Tài khoản demo | ✅ | `admin / Admin@123`, `user / User@123` |

### Cơ chế sao lưu và phục hồi

| Bước | Mô tả |
|---|---|
| Sao lưu | SQLite Online Backup API (an toàn khi website đang chạy). Ngay sau khi sao lưu: `integrity_check`, đếm số dòng 13 bảng, tính SHA-256; lưu kèm tệp `.json` mô tả |
| Trước khi phục hồi | So SHA-256 (tệp bị sửa thì từ chối, HTTP 409); kiểm tra toàn vẹn bản sao lưu; tự tạo bản an toàn `_truoc-phuc-hoi` từ dữ liệu hiện tại |
| Phục hồi | Ghi bản sao lưu vào CSDL đang chạy bằng Backup API |
| Sau khi phục hồi | Kiểm tra toàn vẹn, khóa ngoại, so số dòng 13 bảng với bản sao lưu; hiển thị bảng kết quả Khớp / Lệch |
| Tải lên (đợt 3) | Nhận tệp `.db` từ máy khác: phải đúng định dạng SQLite, đủ 13 bảng và các cột, không có view/trigger lạ, có tài khoản Admin, qua `integrity_check`. Tệp hợp lệ thành một bản sao lưu (đuôi `_tai-len`); phục hồi vẫn đi qua các bước trên. Bản sao lưu cũ thiếu cột mới được tự bổ sung sau phục hồi |
| Bảo mật | Chỉ Admin; tên tệp kiểm tra bằng regex nên không truy cập được tệp ngoài thư mục `dataset/backups/` |

- **Kiểm thử bằng code** (`test_backup.py`): sao lưu → xóa, thêm và sửa giá sản phẩm → phục hồi. Sau đó đối chiếu **độc lập**: số dòng từng bảng và giá mới nhất của từng sản phẩm đều trùng khớp với lúc sao lưu.
- **Kiểm thử trên giao diện** (TC17): xóa 1 sản phẩm → phục hồi → 13/13 bảng khớp, và sản phẩm đã xóa xuất hiện lại.

**Lưu ý trung thực:** tiêu chí ghi "vẽ sơ đồ **trước khi** lập trình". Tài liệu sơ đồ hiện có được lập sau, dựa trên website đã hoàn thiện. Nếu nhóm có bản phác thảo ban đầu (giấy, Figma...), nên đính kèm thêm vào `reports/`.

---

## 7. Đợt 3: thu thập trên website, review, sao lưu tải lên, giao diện mới

### 7.1. Chức năng mới

| Chức năng | Mô tả |
|---|---|
| Trang **Thu thập dữ liệu** (Admin) | Gọi `crawl.run()` chạy nền (thread), nhật ký cập nhật mỗi 2 giây, nút Dừng; tự nhập lượng dữ liệu (số trang, số sản phẩm/trang review, giãn cách ≥ 1 giây), mẫu nhanh, ước tính thời gian; **lịch tự động** (chu kỳ giờ/ngày, giờ chạy lần đầu, lưu ở `app_settings`); lịch sử các lần chạy |
| Review | Tên người đánh giá dạng rút gọn; review **Cocolux** qua API công khai; ưu tiên sản phẩm còn thiếu review; trang Tra cứu chỉ tải review của sản phẩm đang xem |
| Sao lưu | **Tải lên** tệp `.db` để phục hồi bản dữ liệu khác (xem mục 6) |
| Giao diện | Trang đăng nhập mới (số liệu thật từ `/api/public-stats`); sidebar nổi, banner đầu trang nền tối, thẻ/ô nhập bo tròn đồng bộ ở mọi trang |
| Vận hành | `stop.*`, `restart.*`; `run.*` tự tắt server cũ |

### 7.2. Lỗi tìm thấy và đã sửa

| # | Mức | Lỗi | Hậu quả | Đã sửa |
|---|---|---|---|---|
| R1 | 🟠 | Website hiện cùng một review trên mọi biến thể, nhưng review chỉ gắn vào 1 biến thể; crawler còn mặc định không thêm review mới | Nhiều sản phẩm có lượt đánh giá trên website mà trang Tra cứu trống (Hasaki: 631 sản phẩm thiếu) | Bảng `review_links` nối review với các biến thể (review vẫn lưu 1 lần, thống kê không đếm trùng); mặc định thêm review mới cho sản phẩm đã có. Lần bù thử: 28.138 review thu được → 718 review mới, 22.859 liên kết biến thể, bổ sung tên 4.805 review |
| R2 | 🟡 | Truy vấn Q6 dùng `SUM(is_bought = 1)`: nguồn mà mọi review đều không có thông tin "đã mua" (Cocolux) trả **NULL** thay vì 0 | Kiểm tra CSDL báo FAIL, số liệu thống kê sai | `SUM(CASE WHEN is_bought = 1 THEN 1 ELSE 0 END)` |
| R3 | 🟡 | Trang đăng nhập ghi cứng "5.657 sản phẩm, 6.673 đánh giá" | Lệch ngay khi dữ liệu thay đổi | Lấy từ `/api/public-stats` (chỉ số tổng, không lộ dữ liệu chi tiết) |
| R4 | 🟡 | Windows cho 2 server mở trùng cổng 5000; chạy `run.bat` lần 2 khi cửa sổ cũ còn mở | Trang lúc gọi code mới, lúc gọi code cũ, báo thiếu `/api/crawl` | `run.*` tự tắt server cũ; `app.py` dừng kèm hướng dẫn nếu cổng đã có server; API không tồn tại trả mã `API_NOT_FOUND` và giao diện hướng dẫn khởi động lại |
| R5 | 🟡 | Trang Tra cứu và Báo cáo tải **toàn bộ** review về trình duyệt | Chậm dần khi số review tăng | `/api/reviews?product_id=`, `/api/reviews/counts`, `?fields=stats` |
| R6 | ⚪ | Tên nhà bán lẻ "The Gioi Skin Food" không dấu trên mọi biểu đồ | Hiển thị sai tên thương hiệu | Đổi tên hiển thị khi dựng CSDL |
| R7 | ⚪ | `verify_database.py` không nhận lần chạy chỉ lấy review; chống trùng review khác crawler | Có thể báo FAIL sai sau khi thu thập review | Đọc cả bước `(review)` trong `etl_log`; chống trùng theo (nguồn, `review_id`) giống crawler |
| R8 | ⚪ | Tên tài khoản dạng `_abc123` bị rút gọn thành `_***` | Tên hiển thị khó hiểu | Lấy ký tự chữ/số đầu tiên |

### 7.3. Đánh giá công cụ `crawl_guardian_updated.py` (do ChatGPT viết, nhóm đưa vào xem xét)

Không tích hợp, vì:
1. Sửa sai bộ đọc robots.txt (`replace(r"**\\***", ...)`), nên luật có `*` (VD `Disallow: /*?`) không còn khớp, ảnh hưởng **mọi nguồn**.
2. Gọi `/review/product/listAjax/...`, đường dẫn robots.txt của Guardian cấm (`Disallow: /review/`) và bị Cloudflare chặn.
3. Chế độ đọc HTML đã lưu gán review của 1 sản phẩm cho **toàn bộ** sản phẩm Guardian.
4. `run()` nhận tham số mới nhưng không gọi hàm nào; hàm nạp không ghi `etl_log` và không kiểm tra sản phẩm tồn tại.
