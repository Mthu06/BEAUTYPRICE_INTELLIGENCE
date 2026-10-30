# BeautyPrice Intelligence

Hệ thống thu thập, làm sạch, phân tích và dự đoán giá mỹ phẩm từ 5 nhà bán lẻ trực tuyến tại Việt Nam: Cocolux, Guardian, Hasaki, Thế Giới Skin Food và Watsons.

Đây là đồ án môn **Phân tích dữ liệu lớn trong kinh doanh** (ABDA433708).

## Chạy nhanh

Chỉ cần cài **Python 3.9+**. Không cần MySQL hay bất kỳ server CSDL nào.

| Hệ điều hành | Lệnh |
|---|---|
| **Máy mới, chưa cài gì** | Windows: nháy đúp `cai-dat.bat` · macOS/Linux: `./cai-dat.sh` (tự kiểm tra Python, tạo môi trường ảo, cài thư viện, mở web) |
| Windows (đã cài rồi) | Nháy đúp `run.bat` |
| macOS / Linux | `chmod +x run.sh && ./run.sh` |
| Tắt server | `stop.bat` / `./stop.sh` (chỉ tắt tiến trình Python đang chạy ở cổng của dự án) |
| Khởi động lại (sau khi cập nhật code) | `restart.bat` / `./restart.sh` |
| Khôi phục dữ liệu gốc | `reset.bat` / `./reset.sh` (lấy lại CSDL gốc từ git, kèm kết quả mô hình; không có git thì dựng lại từ `dataset/raw`) |
| Chia sẻ cho máy khác trong mạng LAN | `chia-se-lan.bat` / `./chia-se-lan.sh` (một máy làm server, các máy khác chỉ mở trình duyệt) |

Script tự tạo môi trường ảo, cài Flask, khởi động server và mở **http://127.0.0.1:5000/**. Nếu chưa có `dataset/beautyprice.db`, backend tự dựng CSDL từ `dataset/raw/`.

| Tài khoản | Mật khẩu | Quyền |
|---|---|---|
| admin | Admin@123 | Xem, thêm, sửa, xóa sản phẩm, xuất báo cáo |
| user | User@123 | Xem, xuất báo cáo |

## Chức năng

| Trang | Nội dung |
|---|---|
| Tổng quan | KPI, bộ lọc, tỷ trọng nhà bán lẻ, phân bố giá, giá theo danh mục, xu hướng giá theo ngày, mức giảm giá, top thương hiệu, nhận định |
| Tra cứu dữ liệu | Tìm kiếm không dấu, lọc nhiều tiêu chí, **CRUD** sản phẩm (admin), lịch sử giá, review đã thu thập, xuất CSV |
| Phân khúc (K-Means) | Chọn k theo silhouette, đặc điểm từng cụm, cơ cấu nhà bán lẻ, danh sách sản phẩm theo cụm |
| Dự đoán giá | Hồi quy giá (so sánh 4 mô hình), phân loại phân khúc giá (ma trận nhầm lẫn), độ quan trọng đặc trưng, bảng dự đoán tập test |
| Phát hiện bất thường | Isolation Forest, lý do bất thường, tỷ lệ theo nhà bán lẻ, độ nhạy contamination |
| Báo cáo thống kê | Thống kê tổng quan, **danh sách min – max**, phân bố, đánh giá khách hàng, **chất lượng dữ liệu và quy trình làm sạch**, in/PDF, xuất CSV |
| Thu thập dữ liệu (Admin) | Gọi công cụ thu thập đa nguồn từ website: chọn nguồn, danh mục, **tự nhập lượng dữ liệu** (số trang, số sản phẩm lấy review, số trang review, giãn cách), mẫu nhanh, ước tính thời gian; chạy nền có nhật ký và nút Dừng; **lịch tự động** (chu kỳ giờ/ngày tùy chọn, giờ chạy lần đầu); lịch sử các lần chạy |
| Sao lưu & phục hồi (Admin) | Sao lưu CSDL bằng SQLite Online Backup API; phục hồi có **kiểm tra lại** toàn vẹn, khóa ngoại và số dòng 13 bảng; tự tạo bản an toàn trước khi phục hồi; tải bản sao lưu về máy; **tải lên tệp .db** (từ máy khác) để phục hồi, có kiểm tra định dạng, cấu trúc bảng, view/trigger lạ, tài khoản quản trị |

## Quy trình dữ liệu

```
5 website ──crawl.py──▶ dataset/crawl/crawl_<thời điểm>/ ─┐
                         (thu thập đa nguồn)               ├─▶ dataset/beautyprice.db ──train_models.py──▶ bảng ml_* + dataset/models/
dataset/raw/*.csv ──build_database.py (làm sạch) ──────────┘          (SQLite)              (scikit-learn)
                                                                          ▲
                                                                          └── Flask API (app.py) ◀──▶ giao diện web
```

### Thu thập dữ liệu mới (đa nguồn)

```bash
cd source-code/crawler
python crawl.py --list                     # xem nguồn và danh mục hỗ trợ
python crawl.py                            # mọi nguồn, 6 danh mục, tối đa 3 trang/danh mục, nạp thẳng vào CSDL
python crawl.py --max-pages 0              # thu thập toàn bộ (không giới hạn trang)
python crawl.py --reviews --review-products 50 --review-pages 2   # kèm review Hasaki, bổ sung tên người đánh giá
python crawl.py --delay 2                  # giãn cách 2 giây giữa 2 yêu cầu tới cùng website
python crawl.py --add-new-products         # cho phép thêm sản phẩm mới (mặc định tắt)
python crawl.py --reviews --names-only     # không thêm review mới, chỉ bổ sung tên cho review đã có
python crawl.py --sources hasaki,guardian --categories serum --dry-run   # chạy thử, không ghi CSDL
```

Hoặc dùng trang **Thu thập dữ liệu** trên website (tài khoản admin): cùng các tùy chọn trên, chạy nền, xem tiến trình và đặt lịch tự động.

- Chỉ dùng thư viện chuẩn của Python, không cần cài thêm.
- Nguồn hỗ trợ:
  - **Hasaki**, **Cocolux**, **Thế Giới Skin Food**: lấy qua API JSON công khai mà chính website dùng.
  - **Guardian**: phân tích HTML trang danh mục.
  - **Watsons** (Akamai) và **Guardian** (Cloudflare, từ 10/2026): website bật chống bot. Công cụ chỉ ghi nhận trạng thái `blocked`,
    **không giải captcha / vượt rào**. Review Guardian hiện có là từ dữ liệu gốc.
- Công cụ tuân thủ `robots.txt`, giãn cách giữa các yêu cầu (mặc định 1,5 giây, tối thiểu 1 giây), và lưu dữ liệu thô (nén `.gz`) để truy vết.
- Mỗi lần chạy sinh **snapshot giá mới**. Sản phẩm đã có được nhận ra nhờ dùng cùng công thức mã sản phẩm với dữ liệu gốc, nên lịch sử giá được nối tiếp.
- Mặc định **không thêm sản phẩm mới**: danh sách sản phẩm giữ nguyên như dữ liệu gốc (5.657 sản phẩm), chỉ lịch sử giá dài thêm.
- Review **Hasaki** và **Cocolux** (API review công khai của trang sản phẩm, robots.txt cho phép): thêm review mới cho sản phẩm đã có
  (ưu tiên sản phẩm còn thiếu review), tên người đánh giá chỉ lưu dạng rút gọn (VD “Nguyễn V. A.”). Website hiện cùng một review
  trên mọi biến thể: review chỉ lưu 1 lần, biến thể khác được nối qua bảng `review_links`. Chọn nguồn: `--review-sources hasaki,cocolux`.
- `build_database.py` mặc định chỉ dựng từ `dataset/raw/`; thêm `--with-crawl` để nạp lại cả các lần thu thập trong `dataset/crawl/`.

```bash
cd source-code/pipeline
python build_database.py --force              # dựng lại CSDL từ dữ liệu thô (bản cũ được sao lưu .bak)
pip install -r requirements-ml.txt
python train_models.py                        # huấn luyện lại 4 nhóm mô hình, ghi kết quả vào CSDL
```

Lưu ý: dựng lại CSDL sẽ xóa các thay đổi admin đã nhập qua website (bản cũ vẫn còn trong file `.bak`).

## Cấu trúc thư mục

```
├─ readme.txt                 thông tin đề tài & nhóm (theo mẫu nộp bài)
├─ cai-dat.bat / cai-dat.sh   cài đặt trên máy mới (Python + thư viện)
├─ chia-se-lan.*              một máy làm server cho cả nhóm trong mạng LAN
├─ run.bat / run.sh           chạy 1 lần bấm (stop: tắt · restart: khởi động lại · reset: khôi phục dữ liệu gốc)
├─ source-code/
│  ├─ backend/                app.py (Flask + SQLite), requirements.txt
│  ├─ frontend/               7 trang web, common.js, style.css, vendor/chart.umd.min.js
│  ├─ crawler/                crawl.py: thu thập đa nguồn (Hasaki, Cocolux, Thế Giới Skin Food, Guardian, Watsons)
│  ├─ pipeline/               schema.sql, build_database.py, train_models.py, requirements-ml.txt
│  ├─ analysis/               EDA, KPI, dashboard offline, insight (Giai đoạn 6)
│  └─ tests/                  test_api.py, test_backup.py, test_crawler.py, e2e/ (test case giao diện)
├─ dataset/                   raw/ (CSV gốc), crawl/ (các lần thu thập mới), beautyprice.db, models/, backups/ (bản sao lưu)
├─ reports/                   BAO_CAO_DO_AN.docx/.pdf, SLIDES_BAO_CAO.pptx/.pdf, BANG_PHAN_CONG.md, KICH_BAN_VIDEO.md,
│                             GIAI_THICH_CODE.md, THIET_KE_CSDL.md, KIEM_TRA_CSDL.md, KET_QUA_MO_HINH.md, SO_DO_MAN_HINH.md, TEST_CASES.md, BAO_CAO_LOI.md, demo/
├─ refs/                      tài liệu tham khảo, kết quả mô hình bản trước
└─ libs/                      danh sách phần mềm & thư viện
```

## Kiểm thử

```bash
cd source-code/backend
.venv/Scripts/python ../tests/test_api.py       # Windows (sau khi chạy run.bat ít nhất 1 lần); macOS/Linux: .venv/bin/python
.venv/Scripts/python ../tests/test_backup.py    # sao lưu -> thay đổi dữ liệu -> phục hồi -> đối chiếu
.venv/Scripts/python ../tests/test_crawler.py   # công cụ thu thập (không cần mạng)
```

Test case giao diện (21 trường hợp, tự chụp ảnh, xuất tệp và quay video):
- Kết quả và bằng chứng nằm ở `reports/TEST_CASES.md` và `reports/demo/`.
- Chạy lại bằng `cd source-code/tests/e2e && npm install && node testcases.js http://127.0.0.1:5000 <thư mục kết quả>`. Cần Chrome và `ffmpeg` để quay video; nên chạy với CSDL bản sao vì test có thêm/xóa dữ liệu.

Tài liệu trong `reports/`:
- `BAO_CAO_DO_AN.docx` / `.pdf`: quyển báo cáo đồ án; `SLIDES_BAO_CAO.pptx` / `.pdf`: slides thuyết trình (15 trang).
- `BANG_PHAN_CONG.md`: bảng phân công công việc; `KICH_BAN_VIDEO.md`: kịch bản video (phụ đề ở `demo/phu_de_video.srt`).
- `GIAI_THICH_CODE.md`: giải thích code từ tổng quan tới từng file/hàm, lưu ý và câu hỏi vấn đáp thường gặp.
- `THIET_KE_CSDL.md`: ERD, từ điển dữ liệu, quy tắc nghiệp vụ; `KIEM_TRA_CSDL.md`: kết quả kiểm tra CSDL (tự sinh).
- `KET_QUA_MO_HINH.md`: kết quả 4 nhóm mô hình học máy.
- `SO_DO_MAN_HINH.md`: sơ đồ màn hình, luồng người dùng, ma trận phân quyền, wireframe.
- `TEST_CASES.md`: test case kèm bằng chứng; `BAO_CAO_LOI.md`: rà soát lỗi và các đợt nâng cấp.

## Biến môi trường (tùy chọn)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BEAUTY_PORT` | 5000 | Cổng server |
| `BEAUTY_HOST` | 127.0.0.1 | Đặt `0.0.0.0` để máy khác trong mạng LAN truy cập |
| `BEAUTY_DB` | dataset/beautyprice.db | Đường dẫn CSDL |
| `BEAUTY_ADMIN_PASSWORD` / `BEAUTY_USER_PASSWORD` | Admin@123 / User@123 | Mật khẩu khởi tạo (chỉ áp dụng khi bảng users còn trống) |
| `BEAUTY_SESSION_TTL` | 28800 | Thời gian sống của phiên đăng nhập (giây) |
| `BEAUTY_NO_BROWSER` | — | Đặt `1` để run.bat / run.sh không tự mở trình duyệt |

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| "Không kết nối được backend" | Chạy `run.bat` / `run.sh`, mở bằng `http://127.0.0.1:5000/`, **không** mở file HTML trực tiếp |
| Trang báo "Máy chủ đang chạy chưa có chức năng này" | Server đang chạy bản code cũ: chạy `restart.bat` / `./restart.sh` rồi tải lại trang |
| `did not find executable at ...python.exe` khi chạy `run.bat` | Thư mục `.venv` trỏ tới bản Python đã bị gỡ. Từ bản này `run.bat` tự nhận ra và dựng lại `.venv`; nếu vẫn lỗi, xóa `source-code/backend/.venv` rồi chạy `cai-dat.bat` |
| Máy không có mạng | `cai-dat.bat` / `run.bat` cài Flask từ `libs/wheels` nên vẫn chạy được; chỉ phần huấn luyện lại mô hình mới cần mạng |
| Dữ liệu bị sửa hỏng, muốn về như ban đầu | `reset.bat` / `./reset.sh`. Script lấy lại CSDL gốc **từ git** (có sẵn kết quả mô hình, không cần cài thêm gì); không có git thì dựng lại từ `dataset/raw` |
| Cài thư viện học máy báo lỗi `Preparing metadata ... did not run successfully` / cần `vswhere.exe` | Python đang dùng quá mới nên không có bản dựng sẵn, pip phải biên dịch. Dùng `reset.bat` để lấy CSDL gốc từ git (đã có kết quả mô hình), hoặc cài Python 3.11/3.12 rồi xóa `source-code/backend/.venv` và chạy lại `run.bat` |
| Bị đẩy về trang đăng nhập | Server vừa khởi động lại nên phiên cũ hết hiệu lực. Đăng nhập lại |
| Cổng 5000 bận (macOS AirPlay) | `BEAUTY_PORT=5050 ./run.sh` |
| Muốn xem dữ liệu bằng giao diện | Mở `dataset/beautyprice.db` bằng DB Browser for SQLite |
