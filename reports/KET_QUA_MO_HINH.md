# Kết quả mô hình học máy — BeautyPrice Intelligence (Giai đoạn 7)

- **Script:** [`source-code/pipeline/train_models.py`](../source-code/pipeline/train_models.py).
- **Mô hình đã lưu:** `dataset/models/*.joblib`.
- **Kết quả chi tiết:** các bảng `ml_*` trong `dataset/beautyprice.db`.
- **Lần huấn luyện:** 29/10/2026, trên **6.413 sản phẩm** (giá mới nhất của mỗi sản phẩm, gồm cả lần thu thập 29/10).

---

## 1. Bài toán

Mọi bài toán đều dựa trên các trường có thật trong dữ liệu thu thập: giá bán, giá niêm yết, thương hiệu, danh mục, nhà bán lẻ, rating, số lượt đánh giá, tên sản phẩm.

| # | Bài toán | Loại | Biến mục tiêu | Câu hỏi kinh doanh |
|---|---|---|---|---|
| 1 | Dự đoán giá bán | Học có giám sát, hồi quy | `current_price_vnd` | Một sản phẩm có thuộc tính như vậy thì giá "hợp lý" khoảng bao nhiêu? |
| 2 | Phân loại phân khúc giá | Học có giám sát, phân loại 3 lớp | Thấp / Trung bình / Cao | Sản phẩm này thuộc phân khúc nào? |
| 3 | Phân cụm sản phẩm | Học không giám sát | — | Thị trường chia thành những nhóm sản phẩm nào? |
| 4 | Phát hiện bất thường | Học không giám sát | — | Sản phẩm nào có giá, mức giảm hoặc rating khác thường, cần rà soát? |

## 2. Biến đầu vào và cách chia dữ liệu

### Hồi quy và phân loại (cùng bộ đặc trưng)

| Đặc trưng | Kiểu | Xử lý |
|---|---|---|
| `brand`, `category`, `product_type`, `retailer_id` | Phân loại | Điền giá trị phổ biến nhất; one-hot; gom nhóm hiếm (< 5 sản phẩm) |
| `category_count` | Số | Số danh mục mà sản phẩm thuộc về |
| `rating` | Số | Rating = 0 được coi là thiếu; điền trung vị + cờ thiếu |
| `review_count_log` | Số | log(1 + số lượt đánh giá) |
| `volume_ml_log`, `weight_g_log`, `pack_count`, `is_combo` | Số | **Trích từ tên sản phẩm** (ví dụ "400ml", "800g", "Bộ 3 món", "Combo") |

- **Không** dùng giá niêm yết hay % giảm làm đầu vào, vì chúng suy ra trực tiếp từ giá (rò rỉ mục tiêu).
- **Hồi quy** học trên **log(giá)** vì giá lệch phải mạnh (trung bình 314 nghìn, trung vị 245 nghìn, tối đa 3,16 triệu). Kết quả được đổi về VNĐ khi đánh giá. Đã thử học thẳng trên giá gốc: kém hơn ở mọi chỉ số trên tập validation (MAE 96.692 so với 94.340; R² 0,567 so với 0,601 trong lần thử trên dữ liệu 5.657 sản phẩm).
- **Phân khúc giá:** ngưỡng là phân vị 1/3 và 2/3 của **tập train**: Thấp ≤ 173.000đ < Trung bình ≤ 349.000đ < Cao.
- **Chia dữ liệu:** train / validation / test = **60 / 20 / 20** (3.847 / 1.283 / 1.283), `random_state = 42`.
  - Chọn mô hình trên tập **validation**.
  - Huấn luyện lại mô hình được chọn trên train + validation.
  - Báo cáo kết quả **một lần** trên tập **test**.

## 3. Baseline và kết quả

### 3.1. Hồi quy giá (tập validation)

| Mô hình | MAE (VNĐ) | RMSE (VNĐ) | R² | MAPE |
|---|---:|---:|---:|---:|
| **Baseline**: Dummy (dự đoán trung vị) | 172.956 | 291.999 | −0,057 | 89,2% |
| Ridge Regression | 104.161 | 198.262 | 0,513 | 47,2% |
| **Random Forest** ★ được chọn | **95.872** | **194.280** | **0,532** | **38,4%** |
| Extra Trees | 99.028 | 209.080 | 0,458 | 39,2% |

**Random Forest trên tập test: MAE 86.783đ · RMSE 184.459đ · R² 0,597 · MAPE 33,1%.** So với baseline, sai số trung bình giảm khoảng 50%.

Sai số theo phân khúc giá thực tế (tập test):

| Phân khúc | Số sản phẩm | Sai số % trung bình |
|---|---:|---:|
| Thấp (≤ 173k) | 440 | 52,8% |
| Trung bình | 421 | **21,1%** |
| Cao (> 349k) | 422 | 24,5% |

### 3.2. Phân loại phân khúc giá (tập validation)

| Mô hình | Accuracy | Precision (macro) | Recall (macro) | F1 (macro) |
|---|---:|---:|---:|---:|
| **Baseline**: Dummy (lớp phổ biến) | 0,330 | 0,110 | 0,333 | 0,166 |
| Logistic Regression | 0,673 | 0,667 | 0,673 | 0,667 |
| **Random Forest** ★ được chọn | **0,684** | **0,678** | **0,682** | **0,677** |
| Extra Trees | 0,682 | 0,676 | 0,681 | 0,676 |

**Random Forest trên tập test: Accuracy 73,7% · F1-macro 0,736.**

Ma trận nhầm lẫn (tập test; hàng là thực tế, cột là dự đoán):

| Thực tế \ Dự đoán | Thấp | Trung bình | Cao | Recall |
|---|---:|---:|---:|---:|
| **Thấp** | **349** | 72 | 19 | 79,3% |
| **Trung bình** | 71 | **266** | 84 | 63,2% |
| **Cao** | 25 | 66 | **331** | 78,4% |

### 3.3. Phân cụm K-Means

- **Đặc trưng:** log(giá), % giảm, rating, log(số lượt đánh giá), số danh mục; cùng danh mục, loại sản phẩm, nhà bán lẻ (one-hot).
- **Chuẩn hóa:** StandardScaler.
- **Chọn k:** thử k = 2…10, chọn theo **silhouette** (tính trên mẫu 3.000 điểm). **k = 6** có silhouette cao nhất, **0,297**.
- **Số sản phẩm mỗi cụm:** 804 / 1.131 / 2.770 / 565 / 1.033 / 110.

### 3.4. Phát hiện bất thường — Isolation Forest

- **Đặc trưng:** log(giá), giá so với trung vị danh mục, % giảm, tỷ lệ niêm yết/bán, rating, log(số lượt đánh giá).
- **Kết quả:** với contamination 5% (300 cây), mô hình đánh dấu **321 / 6.413** sản phẩm.
- **Lý do bất thường:** mỗi sản phẩm được gắn 1–2 đặc trưng lệch nhiều nhất (|z| ≥ 1,5).

Độ nhạy theo tham số contamination:

| Contamination | Số sản phẩm bị đánh dấu |
|---:|---:|
| 2% | 129 |
| **5%** (đang dùng) | **321** |
| 8% | 513 |

## 4. Giải thích kết quả

- **Thương hiệu là yếu tố quyết định giá:** chiếm 39% độ quan trọng ở mô hình hồi quy và 41% ở mô hình phân loại. Tiếp theo là **dung tích** (26% / 19%) và **danh mục** (12% / 13%). Kết quả này hợp lý: cùng một danh mục, giá chủ yếu khác nhau theo thương hiệu và quy cách.
- **Rating và số lượt đánh giá gần như không giúp dự đoán giá** (< 3%). Mức độ được đánh giá cao không gắn với giá đắt hay rẻ.
- **Hàng giá rẻ khó dự đoán theo tỷ lệ phần trăm** (sai số 52,8%): sai lệch 50k trên sản phẩm 80k đã là hơn 60%. Nhóm trung bình và cao chính xác hơn nhiều (khoảng 21–25%).
- **Phân loại nhầm chủ yếu giữa 2 nhóm cạnh nhau** (Thấp ↔ Trung bình, Trung bình ↔ Cao). Chỉ có 44/1.283 trường hợp nhầm Thấp ↔ Cao. Nhóm Trung bình khó nhất (recall 63%) vì nằm giữa 2 ngưỡng.
- **Silhouette khoảng 0,3 nghĩa là các cụm có chồng lấn:** thị trường mỹ phẩm không chia thành những nhóm tách bạch. Các cụm nên dùng để mô tả xu hướng, không phải ranh giới cứng.

## 5. Hạn chế

1. **Dữ liệu ngắn hạn:** chỉ có 5 ngày thu thập (18–21/10 và 29/10/2026). Chưa đủ để mô hình hóa biến động giá theo thời gian hay theo mùa khuyến mãi.
2. **Thiếu đặc trưng quan trọng:** thành phần, công dụng, xuất xứ, kênh (chính hãng hay xách tay) không có trong dữ liệu. Dung tích/khối lượng trích từ tên sản phẩm: 7,7% sản phẩm không có cả hai, và cách trích bằng quy tắc có thể đọc nhầm với tên combo.
3. **Rating thiếu nhiều:** 74,6% sản phẩm không có rating (rating = 0 được coi là chưa có; Thế Giới Skin Food không công khai rating).
4. **Watsons không được cập nhật ngày 29/10** (website chặn truy cập tự động), nên dữ liệu Watsons cũ hơn các nhà bán lẻ khác.
5. **Cùng một sản phẩm ở nhiều nhà bán lẻ chưa được đối chiếu** (`product_matching` mới là ứng viên). Sản phẩm trùng có thể nằm ở cả train lẫn test, làm kết quả hơi lạc quan.
6. **R² test (0,597) thấp hơn bản cũ của nhóm (0,652).** Bản cũ dùng thêm đặc trưng `product_variant` và cách chia khác, nhưng code bản cũ không còn nên không đối chiếu được.
7. **Isolation Forest chỉ ra sản phẩm "cần rà soát",** không khẳng định dữ liệu sai. Tỷ lệ 5% là giả định, không phải số đo.

## 6. Pipeline, tham số và cách chạy lại

| Thành phần | Nơi lưu |
|---|---|
| Pipeline đã huấn luyện (tiền xử lý + mô hình) | `dataset/models/price_regressor.joblib`, `price_segment_classifier.joblib`, `kmeans.joblib`, `isolation_forest.joblib` |
| Tham số, chỉ số validation/test của từng mô hình đã thử | Bảng `ml_runs` (`params_json`, `metrics_json`, `is_selected`) |
| Dự đoán từng sản phẩm, cụm, điểm bất thường, độ quan trọng đặc trưng | `ml_price_predictions`, `ml_clusters`, `ml_anomalies`, `ml_feature_importance` |
| Phiên bản thư viện | `source-code/pipeline/requirements-ml.txt` (scikit-learn 1.6.1, pandas 2.2.3, numpy 2.1.3, joblib 1.4.2) |

```bash
cd source-code/pipeline
pip install -r requirements-ml.txt
python train_models.py        # đọc dataset/beautyprice.db, ghi lại bảng ml_* và dataset/models/
```

- **Lặp lại được:** `random_state = 42` cố định cho cách chia dữ liệu và mọi mô hình. Cùng dữ liệu sẽ cho cùng kết quả. Toàn bộ quá trình mất khoảng 15 giây.
- **Dùng mô hình đã lưu:**
  ```python
  import joblib
  model = joblib.load("dataset/models/price_regressor.joblib")
  import numpy as np
  gia = np.exp(model.predict(df))   # mô hình dự đoán log(giá)
  ```
  Trong đó `df` có đúng các cột ở mục 2.
- **Xem kết quả trên website:** trang **Dự đoán giá**, **Phân khúc** và **Phát hiện bất thường**.
