# Insight BEAUTYPRICE INTELLIGENCE

Phạm vi: 2026-10-18 đến 2026-10-21 (UTC+7). Các nhận định mô tả snapshot trong tập thu thập; chưa phải so sánh cùng sản phẩm đã xác minh.

## I01 — Mặt bằng giá trung vị khác nhau giữa danh mục

Phát hiện: Mặt bằng giá trung vị khác nhau giữa danh mục.

Số liệu: Serum: 397,000 VND (n=1121); Tẩy tế bào chết: 177,000 VND (n=293); 2026-10-18 đến 2026-10-21 (UTC+7).

Ý nghĩa: Khác biệt phản ánh cơ cấu sản phẩm của các danh mục; không phải chênh lệch của cùng sản phẩm.

Hành động: Lọc theo danh mục và thương hiệu khi so sánh mức giá; chỉ so sánh trực tiếp khi đã xác minh tương đương.

Bằng chứng: `Du_lieu_bieu_do!E3:G10`.

## I02 — Đuôi giá cao làm giá trung bình cao hơn trung vị

Phát hiện: Đuôi giá cao làm giá trung bình cao hơn trung vị.

Số liệu: n=6,350; trung bình=316,861.91 VND; trung vị=244,000 VND; IQR=261,000 VND; 314 ứng viên vượt ngưỡng IQR (4.94%). Phạm vi: 2026-10-18 đến 2026-10-21 (UTC+7).

Ý nghĩa: Giá cao có thể liên quan phân khúc, dung tích và quy cách, chưa đủ kết luận là lỗi.

Hành động: Ưu tiên trung vị khi mô tả mặt bằng giá; rà soát ứng viên ngoại lệ trên nguồn và giữ nguyên dữ liệu.

Bằng chứng: `01_ket_qua_eda.xlsx / 02_Numeric_Descriptive và 12_Price_Outlier_Candidates`.

## I03 — Mặt bằng giá catalog khác nhau giữa nhà bán lẻ

Phát hiện: Mặt bằng giá catalog khác nhau giữa nhà bán lẻ.

Số liệu: Cocolux: trung vị 299,000 VND (n=734); Hasaki: 227,000 VND (n=1871). Phạm vi 2026-10-18 đến 2026-10-21 (UTC+7); giá snapshot hợp lệ.

Ý nghĩa: Khác biệt về cơ cấu catalog không chứng minh nơi nào rẻ hơn cho cùng một sản phẩm.

Hành động: Lọc danh mục và thương hiệu để mô tả catalog; chỉ so sánh cùng sản phẩm sau xác minh.

Bằng chứng: `02_ket_qua_bieu_do.xlsx / Du_lieu_bieu_do!I3:K8`.

## I04 — Mức giảm giá tính lại trung bình khác nhau theo retailer

Phát hiện: Mức giảm giá tính lại trung bình khác nhau theo retailer.

Số liệu: Hasaki: 36.78% (n=1820 cặp giá); Cocolux: 16.22% (n=285); chỉ cặp giá dương. Phạm vi: 2026-10-18 đến 2026-10-21 (UTC+7). anomalous_discount (L<P): 0 dòng; loại khỏi discount hợp lệ.

Ý nghĩa: Độ sâu khuyến mãi quan sát được khác nhau; chưa chứng minh retailer có giá cuối cùng thấp hơn.

Hành động: Hiển thị cả giá hiện tại, giá niêm yết và discount tính lại; rà soát discount nguồn lệch giá trị tính lại.

Bằng chứng: `Du_lieu_bieu_do!A16:C21`.

## I05 — Giá hiện tại đầy đủ hơn giá niêm yết

Phát hiện: Giá hiện tại đầy đủ hơn giá niêm yết.

Số liệu: 6,350/6,350 giá hiện tại hợp lệ (100.00%); 1,489/6,350 snapshot thiếu cặp giá hợp lệ (23.45%); discount trung bình chỉ dùng 4,861 cặp. Phạm vi: 2026-10-18 đến 2026-10-21 (UTC+7).

Ý nghĩa: Không thể tính khuyến mãi cho các bản ghi thiếu giá niêm yết; cần công bố mẫu số thay vì coi là không giảm giá.

Hành động: Giữ discount trống khi thiếu cặp giá; ưu tiên bổ sung giá niêm yết từ nguồn thu thập.

Bằng chứng: `01_ket_qua_eda.xlsx / 04_Data_Coverage_Quality; 02_ket_qua_bieu_do.xlsx / Du_lieu_bieu_do!A40:D45`.

## I06 — Chưa đủ cơ sở so sánh cùng sản phẩm giữa nhà bán lẻ

Phát hiện: Chưa đủ cơ sở so sánh cùng sản phẩm giữa nhà bán lẻ.

Số liệu: 151 dòng matching; 0 dòng matched + verified. Mẫu số N_need_matching chưa có phương pháp chính thức trong tài liệu dự án. Trạng thái file matching hiện tại.

Ý nghĩa: Chưa có verified equivalent product matches nên dataset chưa đủ cơ sở kết luận retailer nào có giá thấp nhất cho CÙNG MỘT SẢN PHẨM. Cross-source gap và matching success rate hiện NOT CALCULABLE.

Hành động: Xác minh thương hiệu, biến thể, dung tích/quy cách; phê duyệt N_need_matching trước khi công bố tỷ lệ.

Bằng chứng: `02_kpi_dictionary.xlsx / KPI_dictionary / KPI12, KPI06`.

## I07 — Mẫu review gộp chịu ảnh hưởng mạnh bởi Hasaki

Phát hiện: Mẫu review gộp chịu ảnh hưởng mạnh bởi Hasaki.

Số liệu: Hasaki + Guardian: n=6673 review; 749 cặp nguồn + mã sản phẩm; pooled rating trung bình 4.8998/5, trung vị 5.0/5; 410/6673 dòng có source product-match flag = unknown (6.14%). Khoảng review_date nguồn: 2017-01-11 đến 2026-10-21; không lọc theo ngày thu thập giá. guardian: 410 review (6.14%), rating quan sát 2.5–5/5, trung bình 4.9280/5; source product-match flag counts: {'unknown': 410}; hasaki: 6263 review (93.86%), rating quan sát 4–5/5, trung bình 4.8980/5; source product-match flag counts: {'match': 6263}. This source field is NOT a verified link to price products.

Ý nghĩa: Pooled review metrics không phải comparison cân bằng giữa hai retailer vì tỷ trọng mẫu lệch về Hasaki. Đây là observed rating distribution in the collected sample; không suy rộng cho toàn bộ khách hàng. Cờ nguồn không phải verified link to price products.

Hành động: Xem per-source metrics khi mô tả Hasaki và Guardian; không dùng pooled average để kết luận retailer nào có customer satisfaction cao hơn. Giữ review độc lập với price.

Bằng chứng: `01_ket_qua_eda.xlsx / 03_Categorical_Descriptive, 06_Review_Descriptive, 07_Review_Data_Quality`.

## I08 — Thời gian quan sát ngắn và cơ cấu catalog có thể thay đổi theo ngày

Phát hiện: Thời gian quan sát ngắn và cơ cấu catalog có thể thay đổi theo ngày.

Số liệu: 4 ngày thu thập, 2026-10-18 đến 2026-10-21 (UTC+7); 6,350 snapshot trên 5 retailer.

Ý nghĩa: Đường giá trung bình giữa các ngày có thể bị ảnh hưởng bởi cơ cấu mặt hàng được thu thập, chưa phải lịch sử biến động của cùng sản phẩm.

Hành động: Thu thập lặp cùng sản phẩm đã xác minh ở nhiều thời điểm; chỉ mô tả đợt quan sát hiện tại.

Bằng chứng: `Du_lieu_bieu_do!A29:F33`.

