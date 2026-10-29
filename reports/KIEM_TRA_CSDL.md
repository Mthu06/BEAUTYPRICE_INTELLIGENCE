# Kết quả kiểm tra CSDL (Giai đoạn 5)

- **Chạy lúc:** 29/10/2026 13:40. Script: `source-code/pipeline/verify_database.py`; truy vấn: `source-code/pipeline/queries.sql`.
- **Nguồn đối chiếu:** CSV trong `dataset/raw/` và các lần thu thập crawl_20261029T120321.
- **Cách đối chiếu:** phép tính độc lập bằng Python thuần đọc thẳng CSV, không dùng SQL.
- **Kết luận: ✅ TẤT CẢ PASS**

## 1. Số bản ghi sau import

| Bảng | Đếm lại từ CSV | Trong CSDL | Kết quả |
|---|---:|---:|:---:|
| `retailers` | 5 | 5 | ✅ PASS |
| `products` | 6.413 | 6.413 | ✅ PASS |
| `product_categories` | 7.133 | 7.133 | ✅ PASS |
| `price_snapshots` | 10.424 | 10.424 | ✅ PASS |
| `reviews` | 6.673 | 6.673 | ✅ PASS |
| `product_matching` | 130 | 130 | ✅ PASS |
| `collection_logs` | 57 | 57 | ✅ PASS |

`PRAGMA integrity_check` = **ok**; lỗi khóa ngoại (`PRAGMA foreign_key_check`) = **0**.

Quy tắc đếm lại khớp với quy tắc import:
- `products` và `price_snapshots` = dữ liệu gốc cộng các lần thu thập bằng crawler.
- `product_categories` chỉ gồm 6 danh mục hợp lệ, đã bỏ cặp trùng.
- `product_matching` chỉ gồm dòng có `match_id` và sản phẩm tồn tại. 21 dòng `review_only_candidate` không có `match_id` nên không nạp.
- `reviews` đã bỏ dòng trùng (nguồn + sản phẩm + review_id) và rating ngoài khoảng 1–5.

## 2. Đối chiếu truy vấn với phép tính độc lập

| Truy vấn | Loại | Số dòng | Kết quả |
|---|---|---:|:---:|
| `Q1_find_filter_projection` | find + filter + projection + sort | 33 | ✅ PASS |
| `Q2_sort_limit` | sort + limit | 10 | ✅ PASS |
| `Q3_aggregate_by_retailer` | aggregation ($group) | 5 | ✅ PASS |
| `Q4_filter_count_discount` | filter + aggregation | 5 | ✅ PASS |
| `Q5_aggregate_snapshots_by_day` | aggregation trên lịch sử giá | 12 | ✅ PASS |
| `Q6_aggregate_reviews` | aggregation trên review | 2 | ✅ PASS |
| `Q7_lookup_reviews_per_product` | lookup (join) + sort + limit | 5 | ⓘ Chỉ minh họa |

## 3. Kết quả mẫu (tối đa 5 dòng mỗi truy vấn)

### Q1_find_filter_projection

| product_id | product_name | brand | current_price_vnd |
|---|---|---|---|
| prod_e4ae95b6bf623cc9 | OBAGI MEDICAL Nu-Gen Cellular Renewal Serum 30ML | OBAGI | 3.160.000 |
| prod_31a06404843b6132 | Serum Dưỡng Sáng & Đều Màu Da Vitamin C Obagi Professional-C 20% 30ml | OBAGI | 2.950.000 |
| prod_12fa925e95519e74 | Combo 1 PLC TAY TBC 2% BHA 118ML & 1 PLC SEKHITLCL NIACINAMIDE20% 20ML | PAULA'S CHOICE | 2.643.998 |
| prod_b47246ff918e417b | Combo 1 Nước Uống Làm Đẹp Da Từ Nhau Thai Itoh Naris EX Placenta 50ml  | Unknown | 2.092.995 |
| prod_1821cdfe158fc6eb | TINH CHẤT KHỞI SINH PAULA’S CHOICE NAD+ CELLULARYOUTH LONGEVITY SERUM  | PAULA'S CHOICE | 1.979.000 |

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
| cocolux | 743 | 5.000 | 3.160.000 | 386.426,78 |
| guardian | 1.095 | 31.000 | 3.160.000 | 328.981,27 |
| hasaki | 1.874 | 9.000 | 2.625.000 | 291.560,83 |
| the_gioi_skin_food | 1.018 | 24.000 | 1.548.000 | 291.750,49 |
| watsons | 1.683 | 17.000 | 2.963.000 | 313.357,69 |

### Q4_filter_count_discount

| retailer_id | so_sp |
|---|---|
| cocolux | 18 |
| guardian | 99 |
| hasaki | 1.071 |
| the_gioi_skin_food | 258 |
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

