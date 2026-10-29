----- Thông tin đề tài ---------------------
STT: «điền số thứ tự nhóm»
Tên đề tài: BeautyPrice Intelligence - Thu thập, phân tích và dự đoán giá mỹ phẩm từ 5 nhà bán lẻ trực tuyến tại Việt Nam
Lớp học phần: ABDA433708_«điền xx»
Năm học: HK«x»/«20xx-20xx»
--------------------------------------------
Thông tin nhóm
1. «Họ tên nhóm trưởng» (24126228) - «SĐT» - 24126228@student.hcmute.edu.vn   [git: Mthu06]
2. «Họ tên sinh viên 2» (24126231)                                            [git: TrMinhThu]
3. «Họ tên sinh viên 3» (24126224)                                            [git: NgBichThuy]
4. «Họ tên sinh viên 4» («MSSV»)                                              [git: PDat]
5. «Họ tên sinh viên 5» («MSSV»)                                              [git: NTPThuy]

Phân công công việc chi tiết: reports/BANG_PHAN_CONG.md
Kho mã nguồn: https://github.com/Mthu06/beautyprice-analytics
--------------------------------------------
Cấu trúc thư mục
- source-code/   : mã nguồn
    backend/     : Flask API (app.py) trên CSDL SQLite, phục vụ luôn giao diện web
    frontend/    : giao diện web 9 màn hình (HTML/CSS/JS, Chart.js lưu cục bộ trong vendor/)
    crawler/     : crawl.py - công cụ thu thập giá đa nguồn (5 nhà bán lẻ), nạp thẳng vào CSDL
    pipeline/    : schema.sql, build_database.py (làm sạch + nạp CSDL), train_models.py (học máy),
                   verify_database.py (kiểm chứng độc lập), queries.sql (7 truy vấn mẫu)
    analysis/    : EDA, KPI, dashboard offline, insight (Giai đoạn 6)
    tests/       : kiểm thử backend (21 test) và e2e/ (21 test case giao diện)
- dataset/       : dữ liệu
    raw/         : dữ liệu gốc (CSV) từ 5 nhà bán lẻ
    crawl/       : các lần thu thập mới bằng crawler (dữ liệu thô .gz + snapshots.csv + nhật ký)
    beautyprice.db : CSDL SQLite đã làm sạch (kèm kết quả mô hình)
    models/      : mô hình đã huấn luyện (.joblib)
- reports/       : báo cáo, slides, bảng phân công, tài liệu và bằng chứng demo
    BAO_CAO_DO_AN.docx / .pdf  : quyển báo cáo đồ án
    SLIDES_BAO_CAO.pptx / .pdf : slides thuyết trình (15 trang)
    BANG_PHAN_CONG.md          : bảng phân công công việc
    KICH_BAN_VIDEO.md          : kịch bản video báo cáo
    GIAI_THICH_CODE.md         : giải thích code, dùng để ôn vấn đáp
    THIET_KE_CSDL.md           : ERD, từ điển dữ liệu, quy tắc nghiệp vụ
    KIEM_TRA_CSDL.md           : kết quả kiểm chứng CSDL (tự sinh)
    KET_QUA_MO_HINH.md         : kết quả 4 nhóm mô hình học máy
    SO_DO_MAN_HINH.md          : sơ đồ màn hình, luồng người dùng, phân quyền
    TEST_CASES.md              : 21 test case giao diện kèm bằng chứng
    BAO_CAO_LOI.md             : rà soát lỗi và các đợt nâng cấp
    demo/                      : ảnh chụp từng bước, video, tệp xuất, phụ đề video
- refs/          : tài liệu tham khảo, kết quả mô hình bản trước (lưu trữ)
- libs/          : danh sách phần mềm, thư viện sử dụng
--------------------------------------------
Cách chạy
- Windows: nháy đúp run.bat     - macOS/Linux: ./run.sh
- Mở http://127.0.0.1:5000/   Tài khoản: admin / Admin@123 (quản trị), user / User@123 (chỉ xem)
- Tắt server:         stop.bat    /  ./stop.sh
- Khởi động lại:      restart.bat /  ./restart.sh
- Khôi phục dữ liệu gốc: reset.bat /  ./reset.sh
- Thu thập mới:       cd source-code/crawler  && python crawl.py   (xem: python crawl.py --help)
- Dựng lại CSDL:      cd source-code/pipeline && python build_database.py --force
- Kiểm tra CSDL:      cd source-code/pipeline && python verify_database.py
- Huấn luyện lại:     cd source-code/pipeline && pip install -r requirements-ml.txt && python train_models.py
Yêu cầu: Python 3.9+. Không cần cài máy chủ CSDL (dùng SQLite).
Chi tiết: README.md
--------------------------------------------
Số liệu dữ liệu
- 5.657 sản phẩm · 6.350 bản ghi giá · 6.673 đánh giá · 418 thương hiệu · 5 nhà bán lẻ · 6 danh mục
- Lưu ý: 6.350 là số BẢN GHI GIÁ (cũng là số cặp sản phẩm-danh mục), không phải số sản phẩm.
  Một sản phẩm thuộc nhiều danh mục nên được ghi lại theo từng danh mục.
--------------------------------------------
