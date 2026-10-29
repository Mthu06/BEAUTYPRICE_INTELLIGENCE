----- Thông tin đề tài ---------------------
STT: <số thứ tự nhóm>
Tên đề tài: BeautyPrice Intelligence - Thu thập, phân tích và dự đoán giá mỹ phẩm từ 5 nhà bán lẻ trực tuyến tại Việt Nam
Lớp học phần: ABDA433708_xx
Năm học: HKx/20xx-20xx
--------------------------------------------
Thông tin nhóm
1. Họ tên sinh viên trưởng nhóm (mã số sinh viên trưởng nhóm) – SĐT – Email cá nhân
2. Họ tên sinh viên 2 (mã số sinh viên 2)
3. Họ tên sinh viên 3 (mã số sinh viên 3)
4. Họ tên sinh viên 4 (mã số sinh viên 4)
5. Họ tên sinh viên 5 (mã số sinh viên 5)
--------------------------------------------
Cấu trúc thư mục
- source-code/   : mã nguồn
    backend/     : Flask API (app.py) trên CSDL SQLite, phục vụ luôn giao diện web
    frontend/    : giao diện web (HTML/CSS/JS, Chart.js lưu cục bộ trong vendor/)
    crawler/     : crawl.py - công cụ thu thập giá đa nguồn (5 nhà bán lẻ), nạp thẳng vào CSDL
    pipeline/    : schema.sql, build_database.py (làm sạch + nạp CSDL), train_models.py (học máy)
    analysis/    : EDA, KPI, dashboard offline, insight (Giai đoạn 6)
- dataset/       : dữ liệu
    raw/         : dữ liệu thu thập (CSV) từ 5 nhà bán lẻ
    crawl/       : các lần thu thập mới bằng crawler (dữ liệu thô .gz + snapshots.csv + nhật ký)
    beautyprice.db : CSDL SQLite đã làm sạch (kèm kết quả mô hình)
    models/      : mô hình đã huấn luyện (.joblib)
- reports/       : báo cáo, slides, bảng phân công, tài liệu thiết kế CSDL, báo cáo rà soát lỗi
- refs/          : tài liệu tham khảo, kết quả mô hình bản trước (lưu trữ)
- libs/          : danh sách phần mềm, thư viện sử dụng
--------------------------------------------
Cách chạy
- Windows: nháy đúp run.bat     - macOS/Linux: ./run.sh
- Mở http://127.0.0.1:5000/   Tài khoản: admin / Admin@123 (quản trị), user / User@123 (chỉ xem)
- Thu thập mới:       cd source-code/crawler && python crawl.py   (xem: python crawl.py --help)
- Dựng lại CSDL:      cd source-code/pipeline && python build_database.py --force
- Huấn luyện lại:     cd source-code/pipeline && pip install -r requirements-ml.txt && python train_models.py
Chi tiết: README.md
