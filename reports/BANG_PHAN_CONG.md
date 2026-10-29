# Bảng phân công công việc — BeautyPrice Intelligence

- **Đề tài:** BeautyPrice Intelligence — Thu thập, phân tích và dự đoán giá mỹ phẩm từ 5 nhà bán lẻ trực tuyến tại Việt Nam.
- **Mã học phần:** ABDA433708 · **Nhóm:** «số thứ tự nhóm» · **Số thành viên:** 5.
- **Kho mã nguồn:** https://github.com/Mthu06/beautyprice-analytics

> Cột **Tài khoản Git** dùng để đối chiếu phần việc với lịch sử commit, phục vụ phần vấn đáp cá nhân.
> Các chỗ «…» là thông tin cá nhân nhóm tự điền trước khi nộp.

## 1. Thành viên và phần việc chính

| STT | Họ và tên | MSSV | Tài khoản Git | Nội dung phụ trách |
|---:|---|---|---|---|
| 1 | «Điền họ tên» (Nhóm trưởng) | 24126228 | `Mthu06` | Tích hợp hệ thống, website, công cụ thu thập |
| 2 | «Điền họ tên» | 24126231 | `TrMinhThu` | Phân tích khám phá dữ liệu và dashboard |
| 3 | «Điền họ tên» | 24126224 | `NgBichThuy` | Mô hình học máy |
| 4 | «Điền họ tên» | «Điền MSSV» | `PDat` | Thiết kế cơ sở dữ liệu và lưu trữ |
| 5 | «Điền họ tên» | «Điền MSSV» | `NTPThuy` | Dữ liệu thu thập ban đầu |

## 2. Chi tiết theo giai đoạn

| Giai đoạn | Phụ trách | Công việc cụ thể | Sản phẩm bàn giao |
|---|---|---|---|
| Thu thập dữ liệu ban đầu | `NTPThuy` | Thu thập dữ liệu sản phẩm từ website, lưu dạng CSV để nhóm xử lý tiếp | `dataset/legacy/hasaki_products_pages_1_9.csv` |
| **Giai đoạn 5** — Thiết kế CSDL và lưu trữ | `PDat` | Phân tích đối tượng dữ liệu, thuộc tính, ràng buộc và quy tắc nghiệp vụ; thiết kế lược đồ quan hệ; viết tài liệu thiết kế và kiểm tra CSDL | `dataset/raw/`, `reports/THIET_KE_CSDL.md`, `reports/KIEM_TRA_CSDL.md` |
| **Giai đoạn 6** — EDA và dashboard | `TrMinhThu` | Phân tích khám phá dữ liệu, xây dựng bộ chỉ số KPI, vẽ biểu đồ, viết nhận định về dữ liệu, kiểm thử dashboard | `source-code/analysis/` (01_eda, 02_kpi, 02_ve_bieu_do, 03_insight.md, 04_kiem_thu, 05_validate) |
| **Giai đoạn 7** — Mô hình học máy | `NgBichThuy` | Xây dựng 4 nhóm mô hình (hồi quy, phân loại, phân cụm, phát hiện bất thường), so sánh và chọn mô hình, viết báo cáo kết quả | `source-code/pipeline/train_models.py`, `dataset/models/`, `reports/KET_QUA_MO_HINH.md` |
| **Giai đoạn 8** — Website GUI | `Mthu06` | Backend Flask và 9 màn hình giao diện; đăng nhập và phân quyền; tìm kiếm, lọc, CRUD; kết xuất báo cáo; sao lưu và phục hồi; kiểm thử tự động | `source-code/backend/`, `source-code/frontend/`, `source-code/tests/`, `reports/SO_DO_MAN_HINH.md`, `reports/TEST_CASES.md` |
| **Điểm cộng** — Công cụ thu thập đa nguồn | `Mthu06` | Xây dựng công cụ thu thập 5 nguồn, tuân thủ robots.txt; tích hợp vào website kèm chạy nền và lịch tự động | `source-code/crawler/crawl.py`, trang Thu thập dữ liệu |
| Tổng hợp cuối kỳ | Cả nhóm | Rà soát lỗi, làm sạch lại dữ liệu, viết tài liệu, chuẩn bị quyển báo cáo, slides và video | `reports/BAO_CAO_LOI.md`, `reports/GIAI_THICH_CODE.md`, `reports/BAO_CAO_DO_AN.docx`, `reports/SLIDES_BAO_CAO.pptx` |

## 3. Chuẩn bị vấn đáp

Đề bài chấm vấn đáp cá nhân dựa trên bảng phân công và lịch sử git. Mỗi thành viên cần:

1. **Nắm chắc phần mình phụ trách** — đọc kỹ phần tương ứng trong `reports/GIAI_THICH_CODE.md`, tài liệu này giải thích từ tổng quan tới từng tệp và từng hàm, kèm lưu ý và bộ câu hỏi thường gặp.
2. **Mở được commit của mình trên GitHub** và giải thích được mình đã thay đổi những gì.
3. **Nắm được bức tranh chung** của hệ thống (Phần 1 và 2 của `GIAI_THICH_CODE.md`), vì câu hỏi có thể liên quan tới phần tiếp giáp với người khác.

**Hai việc cần xử lý trước buổi vấn đáp:**

- **Đóng góp trên git đang lệch:** phần lớn commit thuộc về `Mthu06`. Các thành viên nên commit thêm phần việc của mình (ví dụ: cập nhật tài liệu phần mình phụ trách, bổ sung chú thích trong code) để lịch sử git phản ánh đúng bảng phân công.
- **Tài khoản `PDat`** dùng email `pdat105206@gmail.com`; email này cần được xác minh trên GitHub thì commit mới hiển thị đúng tên người đóng góp.

## 4. Xác nhận của nhóm

| Thành viên | Tài khoản Git | Xác nhận phần việc | Ký tên |
|---|---|:---:|---|
| «Điền họ tên» | `Mthu06` | | |
| «Điền họ tên» | `TrMinhThu` | | |
| «Điền họ tên» | `NgBichThuy` | | |
| «Điền họ tên» | `PDat` | | |
| «Điền họ tên» | `NTPThuy` | | |
