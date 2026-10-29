# Matching methodology audit

Audit ngày 26/10/2026 trên các source, CSV và tài liệu hiện có trong project.

`product_matching.csv` chứa các ứng viên với `record_type`, `match_group_id`, `match_status`, `verified_by_human`, `candidate_retailer_count` và ghi chú rà soát. Candidate là dữ liệu cần kiểm tra, chưa phải verified equivalence.

Chưa có tài liệu phương pháp của dự án được phê duyệt xác định `N_records_that_require_matching`/`N_need_matching`: population, đơn vị bản ghi, phạm vi thời gian, quy tắc loại/trùng. Bộ lọc `candidate_retailer_count>=2` trong bản code/tài liệu xuất trước đây là lựa chọn triển khai được tự bổ sung, không đủ căn cứ coi là phương pháp chính thức. Successful Matching Rate hiện trả về trống với `NOT CALCULABLE`, lý do: `Matching denominator (N_need_matching) has not been formally defined.`

Cross-source Price Gap chỉ lấy dòng `match_status=matched` và `verified_by_human=true`, có `match_group_id` đã xác minh biến thể, dung tích và quy cách tương đương. Tính theo từng nhóm tương đương và ngày UTC+7, chọn snapshot hợp lệ cuối cùng của mỗi retailer trong ngày; cần ít nhất hai retailer. Gap nhóm = max−min; thẻ tổng hợp là trung bình các gap nhóm/ngày, bảng chi tiết giữ từng nhóm. Thiếu verified match thì `NOT CALCULABLE`, không thay bằng catalog max−min.

`Overall observed price range` = max−min toàn phạm vi chỉ nằm trong thống kê mô tả EDA. Số dòng ứng viên và số verified được báo như chất lượng dữ liệu, không thay thế mẫu số matching success rate.

Guardian review có định danh sản phẩm nguồn riêng. `product_id_match=unknown` không được xem là mapping đã xác minh sang bảng giá.
