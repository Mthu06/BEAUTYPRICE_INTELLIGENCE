-- =====================================================================
-- Truy vấn mẫu trên CSDL SQLite dataset/beautyprice.db
-- Mỗi truy vấn ghi kèm cú pháp MongoDB tương đương (find / filter / sort / limit / projection / aggregation).
-- Chạy:  sqlite3 dataset/beautyprice.db < source-code/pipeline/queries.sql
--        hoặc: python source-code/pipeline/verify_database.py  (chạy + đối chiếu với phép tính độc lập)
-- Dòng "-- name: ..." dùng để verify_database.py tách từng truy vấn.
-- =====================================================================

-- name: Q1_find_filter_projection
-- Sản phẩm Guardian đang bán trên 1 triệu đồng: chỉ lấy 4 trường (projection), lọc 2 điều kiện (filter).
-- MongoDB: db.products.find({retailer_id: "guardian", current_price_vnd: {$gt: 1000000}},
--                           {_id: 0, product_id: 1, product_name: 1, brand: 1, current_price_vnd: 1})
--                     .sort({current_price_vnd: -1, product_id: 1})
SELECT product_id, product_name, brand, current_price_vnd
FROM v_products
WHERE retailer_id = 'guardian' AND current_price_vnd > 1000000
ORDER BY current_price_vnd DESC, product_id;

-- name: Q2_sort_limit
-- 10 sản phẩm đắt nhất toàn hệ thống (sort + limit).
-- MongoDB: db.products.find({}, {product_id: 1, retailer_id: 1, current_price_vnd: 1})
--                     .sort({current_price_vnd: -1, product_id: 1}).limit(10)
SELECT product_id, retailer_id, current_price_vnd
FROM v_products
ORDER BY current_price_vnd DESC, product_id
LIMIT 10;

-- name: Q3_aggregate_by_retailer
-- Thống kê giá hiện tại theo nhà bán lẻ (aggregation: $group + $sort).
-- MongoDB: db.products.aggregate([
--   {$group: {_id: "$retailer_id", so_sp: {$sum: 1}, gia_min: {$min: "$current_price_vnd"},
--             gia_max: {$max: "$current_price_vnd"}, gia_tb: {$avg: "$current_price_vnd"}}},
--   {$sort: {_id: 1}}])
SELECT retailer_id, COUNT(*) AS so_sp, MIN(current_price_vnd) AS gia_min, MAX(current_price_vnd) AS gia_max,
       ROUND(AVG(current_price_vnd), 2) AS gia_tb
FROM v_products
GROUP BY retailer_id
ORDER BY retailer_id;

-- name: Q4_filter_count_discount
-- Số sản phẩm đang giảm giá trên 30% theo nhà bán lẻ (filter + aggregation).
-- MongoDB: db.products.aggregate([{$match: {discount_percent: {$gt: 30}}},
--                                 {$group: {_id: "$retailer_id", so_sp: {$sum: 1}}}, {$sort: {_id: 1}}])
SELECT retailer_id, COUNT(*) AS so_sp
FROM v_products
WHERE discount_percent > 30
GROUP BY retailer_id
ORDER BY retailer_id;

-- name: Q5_aggregate_snapshots_by_day
-- Số lần ghi nhận giá theo ngày thu thập và nhà bán lẻ (lịch sử giá).
-- MongoDB: db.price_snapshots.aggregate([
--   {$lookup: {from: "products", localField: "product_id", foreignField: "_id", as: "p"}}, {$unwind: "$p"},
--   {$group: {_id: {ngay: {$substr: ["$collected_at", 0, 10]}, retailer: "$p.retailer_id"}, so_snapshot: {$sum: 1}}},
--   {$sort: {"_id.ngay": 1, "_id.retailer": 1}}])
SELECT substr(s.collected_at, 1, 10) AS ngay, p.retailer_id, COUNT(*) AS so_snapshot
FROM price_snapshots s JOIN products p ON p.product_id = s.product_id
GROUP BY ngay, p.retailer_id
ORDER BY ngay, p.retailer_id;

-- name: Q6_aggregate_reviews
-- Thống kê đánh giá theo nguồn: số review, điểm trung bình, tỷ lệ đã mua (mẫu số = review có thông tin).
-- MongoDB: db.reviews.aggregate([{$group: {_id: "$source", so_review: {$sum: 1}, diem_tb: {$avg: "$rating"},
--           da_mua: {$sum: {$cond: [{$eq: ["$is_bought", 1]}, 1, 0]}},
--           co_thong_tin: {$sum: {$cond: [{$ne: ["$is_bought", null]}, 1, 0]}}}}, {$sort: {_id: 1}}])
SELECT source, COUNT(*) AS so_review, ROUND(AVG(rating), 4) AS diem_tb,
       SUM(CASE WHEN is_bought = 1 THEN 1 ELSE 0 END) AS da_mua, SUM(is_bought IS NOT NULL) AS co_thong_tin  -- CASE: nguồn không có thông tin vẫn ra 0, không ra NULL
FROM reviews
GROUP BY source
ORDER BY source;

-- name: Q7_lookup_reviews_per_product
-- 5 sản phẩm có nhiều review thu thập nhất (tham chiếu reviews -> products, tương đương $lookup).
-- MongoDB: db.reviews.aggregate([{$match: {product_id: {$ne: null}}},
--   {$group: {_id: "$product_id", so_review: {$sum: 1}, diem_tb: {$avg: "$rating"}}},
--   {$sort: {so_review: -1, _id: 1}}, {$limit: 5},
--   {$lookup: {from: "products", localField: "_id", foreignField: "_id", as: "p"}}])
SELECT p.product_id, p.product_name, COUNT(*) AS so_review, ROUND(AVG(r.rating), 2) AS diem_tb
FROM reviews r JOIN products p ON p.product_id = r.product_id
GROUP BY p.product_id
ORDER BY so_review DESC, p.product_id
LIMIT 5;
