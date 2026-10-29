# Kết quả kiểm tra CSDL (Giai đoạn 5)

- **Chạy lúc:** 29/10/2026 14:36. Script: `source-code/pipeline/verify_database.py`; truy vấn: `source-code/pipeline/queries.sql`.
- **Nguồn đối chiếu:** CSV trong `dataset/raw/`.
- **Cách đối chiếu:** phép tính độc lập bằng Python thuần đọc thẳng CSV, không dùng SQL.
- **Kết luận: ✅ TẤT CẢ PASS**

## 1. Số bản ghi sau import

| Bảng | Đếm lại từ CSV | Trong CSDL | Kết quả |
|---|---:|---:|:---:|
| `retailers` | 5 | 5 | ✅ PASS |
| `products` | 5.657 | 5.657 | ✅ PASS |
| `product_categories` | 6.350 | 6.350 | ✅ PASS |
| `price_snapshots` | 6.350 | 6.350 | ✅ PASS |
| `reviews` | 6.673 | 6.673 | ✅ PASS |
| `product_matching` | 130 | 130 | ✅ PASS |
| `collection_logs` | 27 | 27 | ✅ PASS |

`PRAGMA integrity_check` = **ok**; lỗi khóa ngoại (`PRAGMA foreign_key_check`) = **0**.

Quy tắc đếm lại khớp với quy tắc import:
- `products` và `price_snapshots` = dữ liệu gốc cộng các lần thu thập bằng crawler.
- `product_categories` chỉ gồm 6 danh mục hợp lệ, đã bỏ cặp trùng.
- `product_matching` chỉ gồm dòng có `match_id` và sản phẩm tồn tại. 21 dòng `review_only_candidate` không có `match_id` nên không nạp.
- `reviews` đã bỏ dòng trùng (nguồn + sản phẩm + review_id) và rating ngoài khoảng 1–5.

## 2. Đối chiếu truy vấn với phép tính độc lập

| Truy vấn | Loại | Số dòng | Kết quả |
|---|---|---:|:---:|
| `Q1_find_filter_projection` | find + filter + projection + sort | 26 | ✅ PASS |
| `Q2_sort_limit` | sort + limit | 10 | ✅ PASS |
| `Q3_aggregate_by_retailer` | aggregation ($group) | 5 | ✅ PASS |
| `Q4_filter_count_discount` | filter + aggregation | 5 | ✅ PASS |
| `Q5_aggregate_snapshots_by_day` | aggregation trên lịch sử giá | 8 | ✅ PASS |
| `Q6_aggregate_reviews` | aggregation trên review | 2 | ✅ PASS |
| `Q7_lookup_reviews_per_product` | lookup (join) + sort + limit | 5 | ⓘ Chỉ minh họa |

## 3. Kết quả mẫu (tối đa 5 dòng mỗi truy vấn)

### Q1_find_filter_projection

| product_id | product_name | brand | current_price_vnd |
|---|---|---|---|
| prod_e4ae95b6bf623cc9 | OBAGI MEDICAL Nu-Gen Cellular Renewal Serum 30ML | OBAGI | 3.160.000 |
| prod_31a06404843b6132 | Serum Dưỡng Sáng & Đều Màu Da Vitamin C Obagi Professional-C 20% 30ml | OBAGI | 2.950.000 |
| prod_b47246ff918e417b | Combo 1 Nước Uống Làm Đẹp Da Từ Nhau Thai Itoh Naris EX Placenta 50ml  | Unknown | 2.686.000 |
| prod_1821cdfe158fc6eb | TINH CHẤT KHỞI SINH PAULA’S CHOICE NAD+ CELLULARYOUTH LONGEVITY SERUM  | PAULA'S CHOICE | 1.979.000 |
| prod_5a1af856b4231791 | TINH CHẤT EUCERIN GIÚP GIẢM DẤU HIỆU LÃO HÓA HYALURON-FILLER EPICELLIN | EUCERIN | 1.758.000 |

### Q2_sort_limit

| product_id | retailer_id | current_price_vnd |
|---|---|---|
| prod_57f1ec9f0d4df555 | cocolux | 3.160.000 |
| prod_e4ae95b6bf623cc9 | guardian | 3.160.000 |
| prod_7012211808a35072 | cocolux | 2.999.000 |
| prod_785d87e52c74dc83 | cocolux | 2.999.000 |
| prod_c47483f0aa98c31e | cocolux | 2.999.000 |

### Q3_aggregate_by_retailer

| retailer_id | so_sp | gia_min | gia_max | gia_tb |
|---|---|---|---|---|
| cocolux | 724 | 5.000 | 3.160.000 | 385.823,34 |
| guardian | 984 | 31.000 | 3.160.000 | 321.794,21 |
| hasaki | 1.767 | 9.000 | 2.625.000 | 287.215,34 |
| the_gioi_skin_food | 499 | 24.000 | 1.409.000 | 279.282,57 |
| watsons | 1.683 | 17.000 | 2.963.000 | 313.357,69 |

### Q4_filter_count_discount

| retailer_id | so_sp |
|---|---|
| cocolux | 18 |
| guardian | 114 |
| hasaki | 1.054 |
| the_gioi_skin_food | 120 |
| watsons | 384 |

### Q5_aggregate_snapshots_by_day

| ngay | retailer_id | so_snapshot |
|---|---|---|
| 2026-10-18 | hasaki | 439 |
| 2026-10-19 | hasaki | 1.111 |
| 2026-10-20 | guardian | 511 |
| 2026-10-20 | hasaki | 321 |
| 2026-10-21 | cocolux | 734 |

### Q6_aggregate_reviews

| source | so_review | diem_tb | da_mua | co_thong_tin |
|---|---|---|---|---|
| guardian | 410 | 4,93 | 410 | 410 |
| hasaki | 6.263 | 4,9 | 4.561 | 6.263 |

### Q7_lookup_reviews_per_product

| product_id | product_name | so_review | diem_tb |
|---|---|---|---|
| prod_56c7e648fee6dec2 | Gel Rửa Mặt Eucerin Cho Da Nhờn Mụn 400ml | 186 | 4,97 |
| prod_bdaecb36a9696e18 | Gel Rửa Mặt Cosrx Tràm Trà, 0.5% BHA Có Độ pH Thấp 150ml | 166 | 4,97 |
| prod_1201166a867a9328 | Nước Tẩy Trang L'Oreal Tươi Mát Cho Da Dầu, Hỗn Hợp 400ml | 151 | 4,82 |
| prod_e76bc0e1e84ee346 | Muối Tắm A Bonne Sữa Bò Làm Sáng & Mềm Mịn Da 350g | 127 | 4,99 |
| prod_0994ac3ffe487658 | Combo Cocoon Big Size Tẩy Da Chết Toàn Thân 600ml & Mặt Từ Cà Phê Đắk  | 121 | 4,98 |

