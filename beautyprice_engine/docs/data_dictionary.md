# TỪ ĐIỂN DỮ LIỆU — BEAUTYPRICE INTELLIGENCE


## 1. Phạm vi và quy ước

- Đường dẫn bảng chuẩn: `data/processed/`.
- Không có `data/sample` trong phạm vi tài liệu này.
- Không dùng file có tên chứa `Copy` làm bản chính thức; không sử dụng `src/collectors/collect_thegioiskinfood_tay_trang_reviews.py`.
- Không đưa `.venv`, browser profile, cookie, dữ liệu thu thập chưa được phép công bố hoặc thông tin nhạy cảm lên GitHub.
- Giá thiếu phải để trống/NULL, không tự thay bằng 0; rating thiếu không phải rating = 0.
- Dữ liệu trong ZIP là ảnh chụp tại thời điểm đóng gói; việc có file không chứng minh script đang chạy thành công hoặc nguồn còn truy cập được.

## 2. Danh mục bảng đã kiểm tra header

### 2.1. `products.csv`

Vai trò: Danh mục sản phẩm theo từng nguồn bán lẻ.
Khóa/định danh: `product_id`.

| Cột | Ý nghĩa | Kiểm tra khuyến nghị |
|---|---|---|
| `product_id` | Mã định danh sản phẩm nội bộ; dùng liên kết các bảng. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `retailer_id` | Mã nhà bán lẻ chứa sản phẩm. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `source` | Tên nguồn thu thập/nhà bán lẻ được ghi trong bản ghi. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `product_name` | Tên sản phẩm lấy từ nguồn và được xử lý theo pipeline. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `brand` | Thương hiệu sản phẩm; có thể thiếu. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `product_url` | URL trang sản phẩm tại nguồn, cần chuẩn hóa khi tạo định danh. | Kiểm tra URL hợp lệ. |
| `product_type` | Loại sản phẩm được parser/QA xác định; không đồng nhất hoàn toàn với bảng category. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |

### 2.2. `product_categories.csv`

Vai trò: Quan hệ nhiều-nhiều giữa sản phẩm và danh mục.
Khóa/định danh: `product_id + category + source + category_source_file (khóa ghép gợi ý, cần kiểm tra)`.

| Cột | Ý nghĩa | Kiểm tra khuyến nghị |
|---|---|---|
| `product_id` | Mã sản phẩm liên kết products.csv. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `category` | Tên danh mục sản phẩm. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `source` | Nguồn gán danh mục. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `category_source_file` | Đường dẫn/tên tệp nguồn dùng để truy vết việc gán danh mục. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |

### 2.3. `price_snapshots.csv`

Vai trò: Lịch sử quan sát giá theo sản phẩm và thời điểm.
Khóa/định danh: `snapshot_id`.

| Cột | Ý nghĩa | Kiểm tra khuyến nghị |
|---|---|---|
| `snapshot_id` | Mã định danh lần quan sát giá. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `product_id` | Mã sản phẩm liên kết products.csv. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `retailer_id` | Mã nhà bán lẻ liên kết retailers.csv. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `source` | Nguồn ghi nhận giá. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `current_price_vnd` | Giá bán quan sát được, đơn vị VND. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `listed_price_vnd` | Giá niêm yết/tham chiếu nếu nguồn cung cấp, đơn vị VND. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `discount_percent` | Tỷ lệ giảm giá phần trăm nếu có; kiểm tra cách tính trước khi phân tích. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `rating` | Điểm đánh giá sản phẩm do nguồn hiển thị, nếu có; thang điểm tùy nguồn. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `review_count` | Số lượng đánh giá do nguồn hiển thị, nếu có. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `collected_at` | Thời điểm quan sát/thu thập; kiểm tra định dạng và múi giờ. | Kiểm tra ngày giờ, múi giờ và giá trị thiếu. |
| `product_url` | URL sản phẩm được quan sát. | Kiểm tra URL hợp lệ. |
| `source_file` | Tệp dữ liệu trung gian cung cấp bản ghi để truy vết. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |

### 2.4. `retailers.csv`

Vai trò: Thông tin nhà bán lẻ và phạm vi dữ liệu.
Khóa/định danh: `retailer_id`.

| Cột | Ý nghĩa | Kiểm tra khuyến nghị |
|---|---|---|
| `retailer_id` | Mã định danh nhà bán lẻ. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `retailer_name` | Tên hiển thị nhà bán lẻ. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `country` | Quốc gia liên quan đến nhà bán lẻ. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `currency` | Đơn vị tiền tệ dùng trong dữ liệu/cấu hình. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `website_url` | Địa chỉ website nhà bán lẻ. | Kiểm tra URL hợp lệ. |
| `is_active` | Cờ trạng thái hoạt động theo dữ liệu/cấu hình; không chứng minh quyền thu thập. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `data_categories` | Danh mục dữ liệu/sản phẩm được khai báo; kiểm tra định dạng lưu thực tế. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |

### 2.5. `product_matching.csv`

Vai trò: Kết quả nhóm/đối sánh sản phẩm giữa các nguồn.
Khóa/định danh: `match_id (kiểm tra tính duy nhất theo phiên bản dữ liệu)`.

| Cột | Ý nghĩa | Kiểm tra khuyến nghị |
|---|---|---|
| `match_id` | Mã bản ghi đối sánh. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `match_group_id` | Mã nhóm sản phẩm được đề xuất là tương đương. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `product_id` | Mã sản phẩm nội bộ. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `retailer_id` | Mã nhà bán lẻ của bản ghi sản phẩm. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `source_product_id` | Mã sản phẩm theo nguồn, nếu có. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `source_product_name` | Tên sản phẩm tại nguồn dùng khi đối sánh. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `match_method` | Phương pháp/chiến lược đối sánh được script ghi nhận. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `match_confidence` | Mức độ tin cậy đối sánh; cần xem logic tính trước khi đặt ngưỡng. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `verified_by_human` | Cờ cho biết kết quả đã được người kiểm tra hay chưa. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `match_status` | Trạng thái kết quả đối sánh; không mặc định mọi nhóm đều đã xác nhận. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |

### 2.6. `product_matching_review.csv`

Vai trò: Danh sách ứng viên đối sánh cần kiểm tra thủ công.
Khóa/định danh: `Không xác nhận khóa đơn duy nhất; kiểm tra tổ hợp product_id + candidate_group_id`.

| Cột | Ý nghĩa | Kiểm tra khuyến nghị |
|---|---|---|
| `product_id` | Mã sản phẩm cần rà soát. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `retailer_id` | Mã nhà bán lẻ. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `candidate_group_id` | Mã nhóm ứng viên đối sánh. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `product_name` | Tên sản phẩm. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `product_url` | URL sản phẩm phục vụ đối chiếu. | Kiểm tra URL hợp lệ. |
| `normalized_name` | Tên đã chuẩn hóa cho mục đích matching. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `candidate_group_size` | Số bản ghi trong nhóm ứng viên. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `candidate_retailer_count` | Số nhà bán lẻ trong nhóm ứng viên. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `review_reason` | Lý do bản ghi/nhóm cần người kiểm tra. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |

### 2.7. `collection_logs.csv`

Vai trò: Nhật ký các lần chạy/hoạt động thu thập đã tổng hợp.
Khóa/định danh: `run_id (cần kiểm tra granularity và tính duy nhất)`.

| Cột | Ý nghĩa | Kiểm tra khuyến nghị |
|---|---|---|
| `run_id` | Mã phiên/lượt chạy được ghi nhận. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `retailer_id` | Mã nhà bán lẻ liên quan. | Không rỗng; kiểm tra duy nhất nếu là khóa. |
| `script_name` | Tên script đã thực hiện. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `started_at` | Thời điểm bắt đầu. | Kiểm tra ngày giờ, múi giờ và giá trị thiếu. |
| `finished_at` | Thời điểm kết thúc. | Kiểm tra ngày giờ, múi giờ và giá trị thiếu. |
| `pages_attempted` | Số trang đã thử xử lý. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `records_found` | Số bản ghi được phát hiện. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `records_saved` | Số bản ghi được lưu. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `records_failed` | Số bản ghi thất bại. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `records_skipped` | Số bản ghi bỏ qua. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |
| `status` | Trạng thái phiên/lượt chạy. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `error_message` | Thông báo lỗi nếu có. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `output_file` | Đường dẫn đầu ra của lượt chạy. | Kiểm tra giá trị thiếu, kiểu và chuẩn hóa. |
| `duration_seconds` | Thời lượng chạy, đơn vị giây. | Kiểm tra số, đơn vị và giá trị không âm nếu phù hợp. |

## 3. Quan hệ dữ liệu và kiểm tra toàn vẹn

- `products.retailer_id` → `retailers.retailer_id` (đối chiếu nếu bảng retailers đã xây dựng).
- `product_categories.product_id` → `products.product_id`. Một sản phẩm có thể có nhiều danh mục; không nhân bản dòng sản phẩm chỉ vì khác danh mục.
- `price_snapshots.product_id` → `products.product_id`; `price_snapshots.retailer_id` → `retailers.retailer_id` khi bảng retailer có đủ bản ghi.
- `product_matching.product_id` và `product_matching_review.product_id` → `products.product_id`.
- `collection_logs.retailer_id` → `retailers.retailer_id` khi giá trị được cung cấp và hợp lệ.
- Các quan hệ này là quy tắc đối chiếu dữ liệu, không phải tuyên bố rằng CSV có cơ chế khóa ngoại tự động.

## 4. Định danh, snapshot và đối sánh

- `product_id`: script build sử dụng định danh ổn định dựa trên nguồn và URL sản phẩm chuẩn hóa; cần giữ nhất quán khi thêm nguồn.
- `snapshot_id`: dùng nhận diện quan sát giá; thời điểm `collected_at` khác nhau có thể tạo các lần quan sát riêng.
- Không ghi đè âm thầm các snapshot có cùng định danh nhưng thông tin giá khác nhau; xem `output/reports/beautyprice_snapshot_conflicts.csv`.
- `product_matching.csv` chứa kết quả/ứng viên nhóm sản phẩm; `product_matching_review.csv` là danh sách cần rà soát, không phải bằng chứng đã ghép đúng.
- Trước khi so sánh giá giữa nhà bán lẻ, kiểm tra thương hiệu, dung tích/khối lượng, quy cách, phiên bản và thời điểm giá. Các thuộc tính này không nhất thiết có cột riêng trong bảng products hiện tại.

## 5. Review và dữ liệu trung gian

- `reviews.csv` là bảng tùy chọn trong mô tả dự án; không phát hiện `data/processed/reviews.csv` ở cấp bảng chuẩn trong ZIP đã kiểm tra. Vì vậy chưa thể công bố một schema chuẩn thống nhất cho bảng này.
- Review thô có thể ở `data/interim/<source>/by_category/`; review sạch/audit có thể ở `data/processed/hasaki_reviews/` và `data/processed/guardian_reviews/`.
- Các file review theo nguồn/phiên bản có thể có header khác nhau; phải đọc header từng tệp trước khi nối dữ liệu.
- Những tên kết quả thường gặp: `*_clean.csv`, `*_review_audit.csv`, `review_quality_report.csv`. Review audit và quality report là tài liệu kiểm soát chất lượng, không thay thế bảng dữ liệu phân tích.
- Không mặc định 0 review là không có đánh giá; cần kiểm tra collector, selector, widget, mạng và log.

## 6. Các script xử lý và đầu ra chính

| Script | Đầu ra mặc định cần kiểm tra |
|---|---|
| `src/processing/build_beautyprice_datasets.py` | `data/processed/products.csv`, `product_categories.csv`, `price_snapshots.csv`; `output/reports/beautyprice_input_report.csv`, `beautyprice_snapshot_conflicts.csv` |
| `src/processing/build_retailers.py` | `data/processed/retailers.csv` |
| `src/processing/build_product_matching.py` | `data/processed/product_matching.csv`, `product_matching_review.csv` |
| `src/processing/build_collection_logs.py` | `data/processed/collection_logs.csv` |
| `src/processing/clean_guardian_reviews.py` | Review clean, audit và quality report theo cấu hình script |
| `src/processing/clean_hasaki_reviews_v2_all_categories.py` | Review clean, audit và quality report theo cấu hình script |

Lưu ý: các bước trên độc lập, không phải chuỗi tự động. Phải kiểm tra input/output và `--help` của đúng phiên bản script trước khi chạy.

## 7. Báo cáo, log và dữ liệu thô

- `output/reports/beautyprice_input_report.csv`: báo cáo dữ liệu đầu vào của bước build.
- `output/reports/beautyprice_snapshot_conflicts.csv`: báo cáo xung đột snapshot.
- `output/reports/hasaki_brand_summary.csv`, `hasaki_data_quality_issues.csv`, `hasaki_data_quality_report.txt`: báo cáo nguồn Hasaki (nếu hiện có/tạo ra theo pipeline).
- `output/logs/collection_events.jsonl`, `hasaki_collection_log.jsonl`: log dạng JSON Lines, không phải CSV.
- `data/raw/`: HTML/JSON gốc để đối chiếu và parse lại; không sửa trực tiếp dữ liệu gốc.
- `data/interim/`: CSV sản phẩm/review theo nguồn, QA, rejected cards và báo cáo trung gian.

## 8. Kiểm tra chất lượng trước khi phân tích

1. Kiểm tra CSV có header đúng và đọc được bằng UTF-8/UTF-8-SIG.
2. Kiểm tra số dòng, khóa trùng, khóa thiếu và quan hệ tham chiếu giữa các bảng.
3. Kiểm tra giá VND, tỷ lệ giảm giá, rating và số review theo định dạng thực tế của từng nguồn.
4. Kiểm tra URL sản phẩm, `source_file`, thời điểm thu thập và múi giờ.
5. Đối chiếu số dòng đầu vào/đầu ra; đọc QA, rejected, audit, input report và conflict report.
6. Rà soát thủ công các nhóm đối sánh chưa xác nhận.
7. Ghi lại phiên bản script, lệnh chạy, thời gian, nguồn, danh mục và đường dẫn output.

## 9. Trạng thái nguồn và giới hạn sử dụng

- Trong `config/sources.json`, Hasaki được gắn `existing_pipeline`; Guardian, Beauty Box và Watsons được gắn `candidate_not_yet_validated`. Đây là nhãn cấu hình, không phải kết quả kiểm thử độc lập.
- Mã nguồn còn có các script liên quan Cocolux và Thế Giới Skinfood. Sự tồn tại của script không chứng minh collector hoạt động hoặc được phép truy cập tự động.
- Không sử dụng file có tên chứa `Copy` làm bản chính thức, và không dùng collector review tẩy trang Thế Giới Skinfood đã bị loại trừ.
- Cần xác minh điều khoản nguồn, quyền truy cập, cấu trúc website và tính hợp lệ của dữ liệu trước khi chạy thu thập.

## 10. Tài liệu liên quan

- `README.md`: tổng quan và hướng dẫn bắt đầu.
- `docs/pipeline.png`: hình minh họa luồng xử lý.
- `docs/dashboard_mockup.png`: giao diện phác thảo, không phải kết quả đã kiểm chứng.
- `BEAUTYPRICE_INTELLIGENCE_HUONG_DAN_HOP_NHAT_CHI_TIET.docx`: tài liệu vận hành/bàn giao chi tiết (nếu được lưu cùng dự án hoặc cung cấp riêng).

---

Tài liệu này ghi nhận schema CSV đã quan sát trong ZIP; nếu script hoặc dữ liệu thay đổi, phải cập nhật lại header, quy tắc và các quan hệ tương ứng.
