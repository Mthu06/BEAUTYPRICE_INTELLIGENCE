# Sơ đồ màn hình và luồng người dùng — BeautyPrice Intelligence

Tài liệu này dùng cho **Giai đoạn 8: Website GUI và chức năng cộng điểm**. Nội dung gồm:
1. Sơ đồ các màn hình và cách điều hướng giữa chúng.
2. Ma trận phân quyền.
3. Luồng người dùng cho các tác vụ chính.
4. Khung bố cục (wireframe) của từng màn hình.

Ảnh chụp thực tế của từng màn hình nằm ở `reports/demo/screens/`.

## 1. Sơ đồ màn hình

```mermaid
flowchart TD
    L[Đăng nhập<br/>login.html] -->|đúng tài khoản| D[Tổng quan<br/>dashboard.html]
    L -->|sai| L
    subgraph Menu["Thanh điều hướng (mọi trang sau đăng nhập)"]
        D
        T[Tra cứu dữ liệu<br/>tracuu.html]
        P[Phân khúc K-Means<br/>phankhuc.html]
        F[Dự đoán giá<br/>dudoan.html]
        A[Phát hiện bất thường<br/>batthuong.html]
        B[Báo cáo thống kê<br/>baocao.html]
        S[Sao lưu & phục hồi<br/>saoluu.html — chỉ Admin]
    end
    T --> TD[Cửa sổ chi tiết:<br/>thông tin, lịch sử giá, review]
    T --> TF[Cửa sổ thêm / sửa sản phẩm — Admin]
    T --> TX[Cửa sổ xác nhận xóa — Admin]
    T --> CSV1[(Tệp CSV danh sách đang lọc)]
    F --> CSV2[(CSV kết quả dự đoán)]
    A --> CSV3[(CSV sản phẩm bất thường)]
    B --> CSV4[(CSV báo cáo nhiều phần)]
    B --> PDF[(In / Lưu PDF)]
    S --> SC[Cửa sổ xác nhận phục hồi]
    SC --> SR[Bảng kết quả kiểm tra<br/>sau phục hồi]
    Menu -->|Đăng xuất| L
```

## 2. Ma trận phân quyền

| Chức năng | Khách (chưa đăng nhập) | User | Admin |
|---|:---:|:---:|:---:|
| Xem Tổng quan, Tra cứu, Phân khúc, Dự đoán, Bất thường, Báo cáo | ✗ (chuyển về đăng nhập) | ✓ | ✓ |
| Tìm kiếm, lọc, xem chi tiết và lịch sử giá | ✗ | ✓ | ✓ |
| Xuất CSV, In / Lưu PDF | ✗ | ✓ | ✓ |
| Thêm, sửa, xóa sản phẩm | ✗ | ✗ (ẩn nút; API trả 403) | ✓ |
| Sao lưu, tải bản sao lưu, phục hồi | ✗ | ✗ (ẩn menu; API trả 403) | ✓ |

Phân quyền được kiểm tra ở **cả hai phía**: giao diện ẩn nút và menu, còn backend chặn bằng token và vai trò (`@require_auth(["Admin"])`). Nếu người dùng sửa vai trò trong trình duyệt, khi tải lại trang hệ thống vẫn lấy vai trò thật từ server (`/api/me`).

Tài khoản demo:

| Tài khoản | Mật khẩu | Vai trò |
|---|---|---|
| `admin` | `Admin@123` | Admin |
| `user` | `User@123` | User |

## 3. Luồng người dùng

### 3.1. Đăng nhập và đăng xuất
```mermaid
sequenceDiagram
    actor U as Người dùng
    participant W as Website
    participant API as Flask API
    U->>W: Mở trang bất kỳ
    W->>W: Chưa có token → chuyển login.html
    U->>W: Nhập tài khoản, mật khẩu
    W->>API: POST /api/login
    alt Sai mật khẩu (sai 5 lần → khóa 5 phút)
        API-->>W: 401 / 429 + thông báo
        W-->>U: Hiện lỗi dưới form
    else Đúng
        API-->>W: token + vai trò
        W-->>U: Vào Tổng quan, menu theo vai trò
    end
    U->>W: Bấm Đăng xuất
    W->>API: POST /api/logout (hủy token)
    W-->>U: Về trang đăng nhập
```

### 3.2. Tra cứu và CRUD sản phẩm (Admin)
```mermaid
flowchart LR
    A[Tra cứu] --> B{Tìm kiếm / lọc<br/>nhà bán lẻ, danh mục,<br/>thương hiệu, giá, giảm giá}
    B --> C[Bảng kết quả + phân trang]
    C -->|bấm tên| D[Chi tiết: lịch sử giá, review]
    C -->|+ Thêm / Sửa| E[Form sản phẩm]
    E --> F{Kiểm tra dữ liệu<br/>giá > 0, niêm yết ≥ giá bán,<br/>link http/https}
    F -->|sai| E
    F -->|đúng| G[(Lưu CSDL)]
    G -->|đổi giá| H[(Thêm snapshot giá mới)]
    C -->|Xóa| I[Xác nhận] --> G
    G --> J[Thông báo + tải lại,<br/>giữ trang đang xem]
    C -->|Xuất CSV| K[(Tệp CSV)]
```

### 3.3. Sao lưu và phục hồi (Admin)
```mermaid
flowchart TD
    A[Sao lưu & phục hồi] -->|Tạo bản sao lưu| B[SQLite Online Backup API]
    B --> C{Kiểm tra bản sao:<br/>integrity_check, đếm dòng, SHA-256}
    C -->|lỗi| X[Báo lỗi]
    C -->|ok| D[Bản sao lưu + tệp .json mô tả]
    A -->|Phục hồi| E[Xác nhận]
    E --> F{SHA-256 khớp?<br/>bản sao lưu toàn vẹn?}
    F -->|không| Y[Từ chối phục hồi - 409]
    F -->|có| G[Tự sao lưu dữ liệu hiện tại<br/>_truoc-phuc-hoi]
    G --> H[Ghi bản sao lưu vào CSDL]
    H --> I{Kiểm tra sau phục hồi:<br/>toàn vẹn, khóa ngoại,<br/>số dòng 13 bảng = bản sao lưu}
    I --> J[Bảng kết quả: Khớp / Lệch]
```

### 3.4. Xem phân tích và xuất báo cáo (User và Admin)
```mermaid
flowchart LR
    D[Tổng quan: KPI, 6 biểu đồ, nhận định] --> P[Phân khúc: chọn k, đặc điểm cụm]
    D --> F[Dự đoán: chỉ số, so sánh mô hình, ma trận nhầm lẫn]
    D --> A[Bất thường: lý do, danh sách cần rà soát]
    D --> B[Báo cáo: min–max, phân bố, đánh giá, chất lượng dữ liệu]
    B --> C[(Xuất CSV)]
    B --> PDF[(In / Lưu PDF)]
```

## 4. Khung bố cục (wireframe)

Bố cục chung của mọi trang sau khi đăng nhập:
```
┌──────────────┬───────────────────────────────────────────────────────────┐
│ ◆ BeautyPrice│  Tiêu đề trang                          [nút thao tác]    │
│              │  Mô tả ngắn                                               │
│ ▣ Tổng quan  ├───────────────────────────────────────────────────────────┤
│ ⌕ Tra cứu    │  [ Bộ lọc: nhà bán lẻ | danh mục | thương hiệu | giá ]    │
│ PHÂN TÍCH    ├──────────┬──────────┬──────────┬──────────┐              │
│ ◉ Phân khúc  │  KPI 1   │  KPI 2   │  KPI 3   │  KPI 4   │              │
│ ↗ Dự đoán    ├──────────┴──────────┼──────────┴──────────┤              │
│ ⚠ Bất thường │   Biểu đồ A         │   Biểu đồ B         │              │
│ BÁO CÁO      ├─────────────────────┼─────────────────────┤              │
│ ▤ Báo cáo    │   Biểu đồ C         │   Biểu đồ D         │              │
│ QUẢN TRỊ*    ├─────────────────────┴─────────────────────┤              │
│ ⛁ Sao lưu    │   Bảng dữ liệu + phân trang / Nhận định   │              │
│              │                                           │              │
│ (A) admin  ⇥ │                                           │              │
└──────────────┴───────────────────────────────────────────────────────────┘
 * chỉ hiện với Admin · Màn hình < 960px: thanh điều hướng thu vào nút ☰
```

| Màn hình | Thành phần chính |
|---|---|
| **Đăng nhập** | Cột trái giới thiệu hệ thống; cột phải là form, nút hiện/ẩn mật khẩu, thông báo lỗi, bấm tài khoản demo để tự điền |
| **Tổng quan** | Bộ lọc → 4 KPI → doughnut tỷ trọng nhà bán lẻ, đường giá theo ngày → cột khoảng giá, cột ngang giá theo danh mục → cột chồng mức giảm, top thương hiệu → nhận định |
| **Tra cứu** | Thanh công cụ (tìm kiếm, 5 bộ lọc, sắp xếp, Xuất CSV, + Thêm) → bảng 50 dòng/trang → cửa sổ chi tiết (lịch sử giá, review), form thêm/sửa, xác nhận xóa |
| **Phân khúc** | 4 KPI → cột số sản phẩm theo cụm, đường silhouette theo k → bubble giá/giảm theo cụm, cột chồng nhà bán lẻ → thẻ đặc điểm cụm → đặc trưng → bảng sản phẩm |
| **Dự đoán** | Hồi quy (KPI, scatter thực tế/dự đoán, so sánh mô hình, độ quan trọng đặc trưng, MAPE theo nhóm) → phân loại (KPI, ma trận nhầm lẫn) → bảng dự đoán tập test |
| **Bất thường** | 4 KPI → scatter giá/giảm, tỷ lệ theo nhà bán lẻ → lý do bất thường, cách mô hình hoạt động, độ nhạy → bảng danh sách cần rà soát |
| **Báo cáo** | Tổng quan → min–max (theo danh mục, nhà bán lẻ, chỉ số) → phân bố → đánh giá → chất lượng dữ liệu → nhận định; nút In/PDF và Xuất CSV |
| **Sao lưu & phục hồi** | 4 KPI trạng thái CSDL → danh sách bản sao lưu (tải về, phục hồi) → bảng kết quả kiểm tra sau phục hồi → mô tả quy trình |
