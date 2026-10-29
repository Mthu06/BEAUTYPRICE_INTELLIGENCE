# Giai đoạn 6 — EDA, KPI và dashboard

## Thứ tự chạy

1. `python 01_eda.py` hoặc Run All `01_eda_beautyprice.ipynb`.
2. `python 02_kpi.py` hoặc Run All `02_kpi_beautyprice.ipynb`.
3. `python 02_ve_bieu_do.py`.
4. `python 05_validate_stage6.py` chạy lại toàn bộ, thực thi các ô code notebook và đối chiếu độc lập từ CSV. Cần Python 3.10+, pandas, openpyxl; Node.js để kiểm thử engine JavaScript. Trình kiểm tra tìm Node trên PATH hoặc runtime có sẵn.

## Đầu ra

- `01_ket_qua_eda.xlsx`: 01_Overview → 02_Numeric_Descriptive → 03_Categorical_Descriptive → 04_Data_Coverage_Quality → 05_Grouped_Price_Statistics → 06_Review_Descriptive → 07_Review_Data_Quality → 08_Discount_Audit → 09_Schema_Inventory. Sheet 10–13 chỉ giữ IQR bổ trợ, trạng thái thu thập, chi tiết ngoại lệ và ghi chú. Không xuất sheet thống kê legacy 3 biến; tỷ lệ trống theo trường được giữ trong schema inventory.
- `02_kpi_dictionary.xlsx`: bộ 10 KPI độc lập, có công thức, đơn vị, điều kiện lọc, thời gian, nguồn và cách kiểm tra.
- `02_ket_qua_bieu_do.xlsx`: giữ 5 biểu đồ giá; 2 biểu đồ review Hasaki + Guardian và bảng bằng chứng ở `Review_Charts`, `Review_Data`.
- `02_dashboard.html`: mở trực tiếp bằng Chrome/Edge, chạy cục bộ không cần mạng. Có tab PRICE và REVIEWS; không có bộ lọc sản phẩm. Các bộ lọc giá không tác động tab review.
- `03_insight.md`: 8 insight theo mẫu phát hiện → số liệu → ý nghĩa → hành động → bằng chứng.
- `04_kiem_thu_dashboard.xlsx`: kết quả đối chiếu KPI và các test case dashboard.
- `05_validation_results.json`: bằng chứng chạy lại, đối chiếu từ dataframe, SHA256 raw CSV và giới hạn kiểm thử.
- `MATCHING_METHODOLOGY.md`: lý do hai KPI matching chưa tính được và điều kiện tính cross-source gap.

## Quy tắc chính

Giá hợp lệ là số hữu hạn lớn hơn 0. Ngoại lệ IQR chỉ được đánh dấu, không tự xóa. Giảm giá hợp lệ cần cặp giá dương và L>=P; L<P được gắn anomalous_discount. Overall observed price range chỉ ở EDA. Cross-source Price Gap chỉ tính trên verified equivalent product/date có >=2 retailer; chưa có verified match thì NOT CALCULABLE. Successful Matching Rate cũng NOT CALCULABLE do chưa có N_need_matching được định nghĩa chính thức.

## Phân biệt discount theo dữ liệu thực tế

| Field | Meaning | Source | Main use |
|---|---|---|---|
| `discount_percent_source` | Giá trị website/nguồn gốc được giữ lại | CSV đầu vào | Truy vết số liệu gốc và đối chiếu sai lệch |
| `discount_percent` | Discount đã được xử lý: giữ nguồn khi đã kiểm tra; thay bằng calculated khi lệch; bổ sung calculated khi nguồn thiếu | CSV đầu vào, kèm `discount_resolution_status` | Thống kê trường discount sau xử lý; không coi mọi giá trị là website gốc |
| `discount_percent_calculated` | Trường tính sẵn trong CSV; dữ liệu thực tế khớp `(L-P)/L*100` làm tròn 2 chữ số | Bước trước Giai đoạn 6; không có mã upstream để xác nhận chính xác bước nào | Kiểm tra giá trị đã tính trước |
| `discount_percent_recalculated` | Giai đoạn 6 tính lại độc lập `(L-P)/L*100`, không làm tròn trước khi tổng hợp | Dataframe EDA, không ghi raw CSV | Numeric validation và discount KPI/dashboard |

Dấu vết hiện có: 4.727 dòng `source_value_validated`, 119 dòng `replaced_by_calculated_value_source_preserved`, 15 dòng `filled_from_valid_price_pair`, 1.489 dòng `missing_not_imputed`. Đây là bằng chứng `discount_percent` không luôn bằng nguồn gốc. Có 0 anomalous discount trong lần kiểm tra hiện tại. Giá trị âm nếu gặp sau này chỉ giữ trong audit với cờ bất thường; valid average dùng P>0, L>0, L>=P. Trường `_percent` ở CSV/EDA lưu thang 0–100; KPI Excel lưu tỷ lệ 0–1 và định dạng phần trăm.

Review analysis scope: Hasaki and Guardian. Đọc đúng một `hasaki_reviews.csv` và một `guardian_reviews.csv` bên trong `dataset/raw` (ở thư mục gốc dự án); giữ nguyên CSV và mọi dòng nguồn. Dashboard có bộ lọc Tất cả / Hasaki / Guardian, kết hợp AND với danh mục. EDA và supporting KPI `Review_Metrics` báo tổng và từng nguồn. Sản phẩm đếm theo cặp `source + source_product_id`, không coi sản phẩm hai nguồn là cùng một sản phẩm đã matching. Giữ nguyên nhãn category mỗi nguồn, không tự gộp tên tương tự. Rating kiểm tra 1–5, giữ nửa sao. Ngày Hasaki `%Y-%m-%d %H:%M:%S`, Guardian ngày tiếng Việt; không thay collected_at. Các tỷ lệ mua hàng/ảnh dùng dòng có trạng thái không trống; `yes/true/1` là true, không tự đổi mẫu số thành toàn bộ khách hàng. Cờ `product_id_match` mô tả dữ liệu nguồn, không chứng minh liên kết với bảng giá; không join giá–rating.

100% of the collected Guardian review records are marked as purchased/is_bought=yes. The collected Guardian review sample is strongly concentrated at high ratings. Hai nhận định chỉ mô tả mẫu đã thu thập, không suy rộng cho toàn bộ khách hàng Guardian hay năm retailer.

Audit theo source nằm tại `01_ket_qua_eda.xlsx / 07_Review_Data_Quality`, với rating hợp lệ/thiếu/sai, review text/ngày thiếu, ngày sai định dạng, duplicate theo source + source_product_id + review_id, mẫu số/cờ true mua hàng và ảnh, source flag counts và tỷ trọng mẫu. Không xóa dòng. Categorical đầy đủ theo nguồn vẫn ở `03_Categorical_Descriptive`. Hasaki: `product_id_match=match` 6.263 dòng, 0 rows marked unknown in the Hasaki source field; Guardian: `unknown` 410 dòng. This source field is NOT a verified link to price products. Không diễn giải cờ `match` là verified price matching.

Tổng 6.673 review: Hasaki 6.263 (93,86%), Guardian 410 (6,14%). Rating quan sát Hasaki 4–5, Guardian 2.5–5 là observed rating distribution in the collected sample. Pooled average chịu ảnh hưởng mạnh bởi Hasaki, không phải comparison cân bằng giữa hai retailer; xem per-source metrics khi mô tả hai mẫu, không dùng pooled average để kết luận mức hài lòng khách hàng.

Notebook lưu đầu ra được thực thi tuần tự bằng Python; môi trường kiểm tra chưa có Jupyter kernel. Để chạy Run All bằng Jupyter/VS Code, chọn kernel có pandas và openpyxl. Các thư viện này không được tự cài qua mạng trong quy trình bàn giao.

Kiểm thử giao diện tùy chọn: `python 02_ve_bieu_do.py --serve-qa --port 8769`, mở `http://127.0.0.1:8769/__qa__`, nhấn nút chạy. Trang riêng đối chiếu thẻ DOM và biểu đồ thật cho PRICE T01–T22, REVIEW T09–T16 (hai phạm vi test riêng), gồm từng nguồn và nguồn + danh mục; lưu log vào workbook 04. Chưa chạy UI thì ghi NOT_RUN. Chạy lại script sinh dashboard sẽ xóa bằng chứng UI cũ để tránh dùng lại PASS cho phiên bản khác.

Khi nộp, dùng hai notebook đã lưu đầu ra, các file Excel 01/02/04, dashboard HTML, insight 03, README và phương pháp matching; kèm các script `.py` và thư mục `dataset/raw` để tái tạo. Không nộp riêng notebook mà thiếu script nó gọi.

Trạng thái kiểm thử ngày 28/10/2026: engine PRICE 22/22 PASS, REVIEW 8/8 PASS; browser QA thực sự chạy trên dashboard hiện tại và đạt UI PRICE 22/22 PASS, REVIEW 8/8 PASS. Bằng chứng: `04_kiem_thu_dashboard.xlsx` (`Test_case`, `Doi_chieu_KPI`, `Log_giao_dien`, `Review_Test_Cases`, `Review_UI_Log`) và `05_validation_results.json` (`dashboard_ui=PASS`, SHA256 dashboard trong `dashboard_ui_evidence`). Nếu regenerate dashboard, phải chạy lại QA cho bản mới trước khi công bố UI PASS. Checklist thủ công trong `MANUAL_DASHBOARD_UI_TEST.md` có thể dùng để kiểm tra bổ sung; `requirements.txt` ghi phiên bản thư viện đã dùng.

Khi server QA đang chạy, có thể chạy `python 05_validate_stage6.py --startup-only` ở terminal thứ hai để ghi bằng chứng HTTP startup vào JSON validation. HTTP PASS chỉ xác nhận server trả đúng HTML hiện tại, không thay thế UI acceptance.
