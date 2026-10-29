# Phần mềm và thư viện sử dụng

## Bắt buộc để chạy website

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| Python | ≥ 3.9 (đã kiểm thử với 3.11) | https://www.python.org/downloads/ |
| SQLite | ≥ 3.25 (có sẵn trong Python) | Hệ quản trị CSDL, không cần cài riêng |
| Flask | ≥ 2.3, < 4 (đã kiểm thử 3.1) | Web framework; xem `source-code/backend/requirements.txt` |
| flask-cors | ≥ 4.0 | Chỉ cần khi mở frontend bằng server khác (Live Server) |
| Werkzeug | đi kèm Flask | Băm mật khẩu PBKDF2-SHA256 |
| Chart.js | 4.4.1 (MIT) | Đã lưu cục bộ tại `source-code/frontend/vendor/chart.umd.min.js`, không cần mạng |
| Trình duyệt | Chrome / Edge / Firefox bản mới | |

`cai-dat.bat` / `cai-dat.sh` (máy mới) và `run.bat` / `run.sh` tự tạo môi trường ảo
`source-code/backend/.venv` rồi cài các thư viện trên.

### Cài được khi không có mạng

Thư mục `libs/wheels/` chứa sẵn gói cài của Flask và các thư viện phụ thuộc (khoảng 730 KB):

| Gói | Vai trò |
|---|---|
| `flask`, `werkzeug`, `jinja2`, `click`, `itsdangerous`, `blinker`, `markupsafe` | Flask và các thư viện phụ thuộc |
| `flask_cors` | Cho phép mở frontend bằng server khác |

Script cài đặt thử `pip install --no-index --find-links libs/wheels` trước; chỉ khi thiếu gói
phù hợp mới tải từ mạng. `markupsafe` có bản riêng cho Python 3.9 đến 3.14 trên Windows 64-bit.
Hệ điều hành khác sẽ tự tải từ mạng.

## Thu thập dữ liệu (`source-code/crawler/crawl.py`)

Chỉ dùng thư viện chuẩn của Python: `urllib`, `json`, `gzip`, `csv`, `re`, `sqlite3`. Không cần cài thêm.

## Huấn luyện mô hình (`source-code/pipeline/requirements-ml.txt`)

| Thư viện | Phiên bản |
|---|---|
| pandas | 2.2.3 |
| numpy | 2.1.3 |
| scikit-learn | 1.6.1 |
| joblib | 1.4.2 |

Mô hình đã dùng: RandomForestRegressor, ExtraTreesRegressor, Ridge, DummyRegressor (hồi quy giá); ExtraTreesClassifier, RandomForestClassifier, LogisticRegression, DummyClassifier (phân loại phân khúc); KMeans + silhouette (phân cụm); IsolationForest (bất thường).

## Phân tích Giai đoạn 6 (`source-code/analysis/requirements.txt`)

| Thư viện | Phiên bản |
|---|---|
| pandas | 3.0.1 (đã chạy được với 2.2.3) |
| openpyxl | 3.1.5 |
| Node.js | tùy chọn, để kiểm thử engine JavaScript của dashboard offline |

## Công cụ hỗ trợ (tùy chọn)

- **DB Browser for SQLite** (https://sqlitebrowser.org/) hoặc extension **SQLite Viewer** trong VS Code: xem bảng, chạy SQL trên `dataset/beautyprice.db`.
- **Jupyter / VS Code**: chạy các notebook `.ipynb` trong `source-code/analysis/`.
