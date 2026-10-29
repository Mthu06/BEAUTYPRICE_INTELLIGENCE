# Test case — Website BeautyPrice Intelligence (Giai đoạn 8)

- **Ngày chạy:** 29/10/2026.
- **Kết quả:** **21/21 PASS**, 0 lỗi JavaScript.
- **Cách chạy:** kịch bản tự động trên Chrome headless (Puppeteer). Kịch bản thao tác trên giao diện như người dùng thật, rồi đối chiếu kết quả với CSDL qua API.
- **Dữ liệu thử:** chạy trên **bản sao** của `dataset/beautyprice.db`, nên CSDL thật không bị thay đổi.
- **Tài khoản:** `admin / Admin@123` (Admin) và `user / User@123` (User).

Bằng chứng nằm trong `reports/demo/`:
- `screens/`: ảnh chụp từng bước.
- `demo.mp4`: video quay lại toàn bộ lượt chạy.
- `exports/`: các tệp xuất.
- `backup_evidence/`: mô tả bản sao lưu.
- `test_results.json`: kết quả gốc.
- `unit_tests_output.txt`: kết quả kiểm thử tự động của backend.

| Mã | Nhóm | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái | Bằng chứng |
|---|---|---|---|---|---|:---:|---|
| TC01 | Đăng nhập | Truy cập trang khi chưa đăng nhập | Mở /dashboard.html khi chưa đăng nhập | Bị chuyển về trang đăng nhập | URL hiện tại: login.html | ✅ PASS | [ảnh](demo/screens/01_dang_nhap.png) |
| TC02 | Đăng nhập | Đăng nhập sai mật khẩu | Nhập admin / matkhausai → Đăng nhập | Hiện thông báo lỗi, không vào hệ thống | Thông báo: "Tài khoản hoặc mật khẩu không đúng!" | ✅ PASS | [ảnh](demo/screens/02_dang_nhap_sai.png) |
| TC03 | Đăng nhập | Đăng nhập admin thành công | Nhập admin / Admin@123 → Đăng nhập | Vào trang Tổng quan, sidebar ghi Quản trị viên và có menu Sao lưu | Trang: dashboard.html, vai trò: Quản trị viên, menu Sao lưu: có | ✅ PASS | [ảnh](demo/screens/03_tong_quan.png) |
| TC04 | Tổng quan | Lọc dashboard theo nhà bán lẻ | Chọn Nhà bán lẻ = Hasaki | KPI Tổng sản phẩm bằng số sản phẩm Hasaki trong CSDL | KPI = 1.874, CSDL = 1.874 | ✅ PASS | [ảnh](demo/screens/04_tong_quan_loc_hasaki.png) |
| TC05 | Tra cứu | Tìm kiếm không dấu | Gõ "kem chong nang" vào ô tìm kiếm | Có kết quả; sản phẩm khớp từ khóa trên tên/thương hiệu/danh mục, không phân biệt dấu (dòng đầu chứa "kem chống nắng") | Hiển thị 1–50 / 1.274 sản phẩm (lọc từ 6.413); dòng đầu: "[50g] Kem Chống Nắng The Saem Kiềm Dầu, Nâng Tone Cho Da Sáng Hồng Pink Sun Cream EX SPF50+/PA++++" | ✅ PASS | [ảnh](demo/screens/05_tra_cuu_tim_kiem.png) |
| TC06 | Tra cứu | Xem chi tiết và lịch sử giá | Tìm một sản phẩm đã đổi giá giữa các lần thu thập → bấm tên sản phẩm | Mở cửa sổ chi tiết, biểu đồ Lịch sử giá có từ 2 điểm trở lên | Sản phẩm "[HSD 01/2027] Gel Rửa Mặt I'm from Từ Ngải Cứu Sạc": biểu đồ có 2 điểm | ✅ PASS | [ảnh](demo/screens/06_chi_tiet_lich_su_gia.png) |
| TC07 | CRUD | Thêm sản phẩm sai dữ liệu | Thêm sản phẩm: giá hiện tại 200.000, giá niêm yết 150.000 → Lưu | Báo lỗi "Giá niêm yết..." trong form, không lưu | Lỗi: "Giá niêm yết phải lớn hơn hoặc bằng giá hiện tại.", form vẫn mở: true | ✅ PASS | [ảnh](demo/screens/07_them_san_pham_loi.png) |
| TC08 | CRUD | Thêm sản phẩm hợp lệ | Sửa giá niêm yết thành 250.000 → Lưu | Thông báo thêm thành công, % giảm tự tính = 20%, tổng sản phẩm tăng 1 | "Thêm sản phẩm thành công!", % giảm hiển thị: 20%, tổng 6413 → 6414 | ✅ PASS | [ảnh](demo/screens/08_them_san_pham_ok.png) |
| TC09 | CRUD | Sửa giá sản phẩm | Tìm sản phẩm vừa thêm → Sửa → giá hiện tại 180.000 → Lưu | Lưu thành công; lịch sử giá có thêm 1 lần cập nhật (2 snapshot) | "Cập nhật sản phẩm thành công!", số snapshot: 2, giá: 200000 → 180000 | ✅ PASS | [ảnh](demo/screens/09_sua_san_pham.png) |
| TC10 | CRUD | Xóa sản phẩm | Bấm Xóa ở sản phẩm vừa thêm → Xác nhận | Thông báo xóa thành công, sản phẩm không còn trong CSDL | "Xóa sản phẩm thành công!", gọi lại API: HTTP 404 | ✅ PASS | [ảnh](demo/screens/10_xoa_san_pham.png) |
| TC11 | Xuất báo cáo | Xuất CSV danh sách đang lọc | Ở trang Tra cứu, tìm "serum" → Xuất CSV | Tải về tệp CSV có dòng tiêu đề và đúng số sản phẩm đang lọc | Tệp tra-cuu-san-pham-2026-10-29.csv: 1542 dòng dữ liệu; trên trang: Hiển thị 1–50 / 1.542 sản phẩm (lọc từ 6.413) | ✅ PASS | [ảnh](demo/screens/11_xuat_csv_tra_cuu.png) |
| TC12 | Mô hình | Trang Phân khúc K-Means | Mở phankhuc.html | Hiện số cụm k, 4 biểu đồ, thẻ đặc điểm cụm | "Phân khúc sản phẩm (K-Means)": 4 biểu đồ, 0 giá trị lỗi (NaN/undefined) | ✅ PASS | [ảnh](demo/screens/12_phan_khuc.png) |
| TC13 | Mô hình | Trang Dự đoán giá | Mở dudoan.html | Hiện MAE/RMSE/R²/MAPE, so sánh mô hình, ma trận nhầm lẫn | "Dự đoán giá (học có giám sát)": 5 biểu đồ, 0 giá trị lỗi (NaN/undefined) | ✅ PASS | [ảnh](demo/screens/13_du_doan.png) |
| TC14 | Mô hình | Trang Phát hiện bất thường | Mở batthuong.html | Hiện số sản phẩm bất thường, biểu đồ, danh sách và lý do | "Phát hiện bất thường (Isolation Forest)": 3 biểu đồ, 0 giá trị lỗi (NaN/undefined) | ✅ PASS | [ảnh](demo/screens/14_bat_thuong.png) |
| TC15 | Xuất báo cáo | Báo cáo thống kê: xuất CSV và PDF | Mở Báo cáo → Xuất CSV; In / Lưu PDF | Tải về CSV nhiều phần; tạo được PDF báo cáo | CSV: bao-cao-thong-ke-2026-10-29.csv; PDF: bao_cao_thong_ke.pdf (404 KB) | ✅ PASS | [ảnh](demo/screens/15_bao_cao.png) |
| TC16 | Sao lưu & phục hồi | Tạo bản sao lưu | Admin mở Sao lưu & phục hồi → Tạo bản sao lưu | Bản sao lưu mới xuất hiện, kiểm tra toàn vẹn = Toàn vẹn, số dòng khớp CSDL hiện tại | "Đã sao lưu và kiểm tra bản sao: beautyprice_20261029T122434.db"; số bản: 0 → 1; integrity=ok; số dòng khớp hiện tại: true | ✅ PASS | [ảnh](demo/screens/16_sao_luu.png) |
| TC17 | Sao lưu & phục hồi | Phục hồi thực tế sau khi dữ liệu bị thay đổi | Xóa 1 sản phẩm (giả lập mất dữ liệu) → Phục hồi bản vừa sao lưu → Xác nhận | Kết quả kiểm tra "khớp 100%" ở cả 13 bảng; sản phẩm đã xóa xuất hiện lại | Đã xóa trước khi phục hồi: true; kết quả: "Đã kiểm tra: khớp 100%" (13 bảng); sản phẩm "[HSD 01/2027] Sữa Rửa Mặt B.O.M Từ 8 Loạ" có lại: true | ✅ PASS | [ảnh](demo/screens/17b_ket_qua_phuc_hoi.png) |
| TC18 | Phân quyền | Tài khoản User chỉ được xem | Đăng nhập user / User@123 → mở Tra cứu | Không có nút Thêm/Sửa/Xóa, không có menu Sao lưu | Nút Thêm: ẩn, nút Sửa/Xóa: 0, menu Sao lưu: không | ✅ PASS | [ảnh](demo/screens/18_user_tra_cuu.png) |
| TC19 | Phân quyền | User gọi API quản trị trực tiếp | Từ trình duyệt của user gọi DELETE /api/products/<id> và GET /api/backups | Backend từ chối với HTTP 403 | DELETE: HTTP 403; /api/backups: HTTP 403; trang Sao lưu: "Chức năng sao lưu & phục hồi chỉ dành cho quản trị viên." | ✅ PASS | [ảnh](demo/screens/19_user_khong_co_quyen.png) |
| TC20 | Đăng nhập | Đăng xuất | Bấm nút Đăng xuất → mở lại /baocao.html | Về trang đăng nhập; mở lại trang bị chuyển về đăng nhập | Sau đăng xuất: login.html; mở lại báo cáo: login.html | ✅ PASS | — |
| TC21 | Giao diện | Hiển thị trên điện thoại | Mở Tổng quan ở màn hình 390px | Không tràn ngang, có nút menu thu gọn | Tràn ngang: false, nút menu: có | ✅ PASS | [ảnh](demo/screens/21_mobile.png) |

## Kiểm thử tự động của backend (`source-code/tests/`)

| Tệp | Nội dung | Kết quả |
|---|---|---|
| `test_api.py` | Đăng nhập và phân quyền; các API đọc dữ liệu; kiểm tra dữ liệu đầu vào; CRUD giữ lịch sử giá | 4/4 OK |
| `test_backup.py` | **Phục hồi thực tế**: sao lưu → xóa/thêm/sửa dữ liệu → phục hồi → đối chiếu độc lập số dòng và giá từng sản phẩm; từ chối tên tệp không hợp lệ; từ chối bản sao lưu bị sửa (sai SHA-256); chỉ Admin được dùng | 4/4 OK |
| `test_crawler.py` | Mã sản phẩm khớp dữ liệu gốc; luật robots.txt; bộ phân tích HTML Guardian; bước làm sạch | 4/4 OK |

Chạy lại:
```bash
cd source-code/backend
.venv/Scripts/python ../tests/test_api.py      # macOS/Linux: .venv/bin/python
.venv/Scripts/python ../tests/test_backup.py
.venv/Scripts/python ../tests/test_crawler.py
```

## Bằng chứng sao lưu / phục hồi

1. `screens/16_sao_luu.png`: tạo bản sao lưu; bản sao được kiểm tra toàn vẹn ngay khi tạo.
2. `screens/17a_xac_nhan_phuc_hoi.png`: xác nhận phục hồi, **sau khi đã xóa 1 sản phẩm** để giả lập mất dữ liệu.
3. `screens/17b_ket_qua_phuc_hoi.png`: kết quả kiểm tra sau phục hồi, 13/13 bảng khớp; sản phẩm đã xóa có lại (TC17).
4. `backup_evidence/*.json`: mô tả bản sao lưu (thời điểm, người tạo, SHA-256, integrity, số dòng từng bảng), gồm cả bản an toàn `_truoc-phuc-hoi` hệ thống tự tạo trước khi phục hồi.
5. `unit_tests_output.txt`, phần `test_backup.py`: kiểm thử phục hồi thực tế bằng code, chạy lại được bất cứ lúc nào.

## Tệp xuất mẫu (`reports/demo/exports/`)

| Tệp | Nguồn |
|---|---|
| `tra-cuu-san-pham-2026-10-29.csv` | Trang Tra cứu → Xuất CSV (danh sách đang lọc "serum") |
| `bao-cao-thong-ke-2026-10-29.csv` | Trang Báo cáo → Xuất CSV (nhiều phần: tổng quan, min–max, phân bố, đánh giá, chất lượng dữ liệu, nhận định) |
| `bao_cao_thong_ke.pdf` | Trang Báo cáo → In / Lưu PDF |
