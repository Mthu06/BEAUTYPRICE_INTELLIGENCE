# Kết quả mô hình học máy — BeautyPrice Intelligence (Giai đoạn 7)

- **Script:** [`source-code/pipeline/train_models.py`](../source-code/pipeline/train_models.py).
- **Mô hình đã lưu:** `dataset/models/*.joblib`.
- **Kết quả chi tiết:** các bảng `ml_*` trong `dataset/beautyprice.db` (website đọc trực tiếp các bảng này).
- **Lần huấn luyện:** 29/10/2026, trên **5.657 sản phẩm** của dữ liệu gốc (giá mới nhất của mỗi sản phẩm, thu thập 18–21/10/2026).

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
- **Hồi quy** học trên **log(giá)** vì giá lệch phải mạnh (trung bình 312.928đ, trung vị 240.000đ, tối đa 3,16 triệu). Dự đoán được đổi lại về VNĐ (`exp`) trước khi tính sai số. Đã thử học thẳng trên giá gốc trong một lần thử nghiệm riêng trên cùng 5.657 sản phẩm: kém hơn ở mọi chỉ số trên tập validation (MAE 96.692 so với 94.340; R² 0,567 so với 0,601).
- **Phân khúc giá:** ngưỡng là phân vị 1/3 và 2/3 của **tập train** (tính trên train rồi mới áp cho validation/test để tránh rò rỉ): Thấp ≤ 169.000đ < Trung bình ≤ 347.000đ < Cao.
- **Chia dữ liệu:** train / validation / test = **60 / 20 / 20** (3.393 / 1.132 / 1.132 sản phẩm), `random_state = 42`.
  - Chọn mô hình trên tập **validation**.
  - Huấn luyện lại mô hình được chọn trên train + validation.
  - Báo cáo kết quả **một lần** trên tập **test**.

## 3. Baseline và kết quả

### 3.1. Hồi quy giá (tập validation)

| Mô hình | MAE (VNĐ) | RMSE (VNĐ) | R² | MAPE |
|---|---:|---:|---:|---:|
| **Baseline**: Dummy (dự đoán trung vị) | 171.288 | 289.568 | −0,057 | 87,9% |
| Ridge Regression | 109.613 | 198.900 | 0,501 | 47,4% |
| **Random Forest** ★ được chọn | **94.089** | **177.891** | **0,601** | **39,2%** |
| Extra Trees | 99.220 | 192.800 | 0,531 | 45,0% |

**Random Forest trên tập test: MAE 90.290đ · RMSE 168.259đ · R² 0,536 · MAPE 35,2%.** So với baseline, sai số tuyệt đối trung bình giảm khoảng 45%.

Sai số theo phân khúc giá thực tế (tập test):

| Phân khúc | Số sản phẩm | Sai số % trung bình |
|---|---:|---:|
| Thấp (≤ 169k) | 386 | 55,8% |
| Trung bình | 377 | **22,6%** |
| Cao (> 347k) | 369 | 26,6% |

### 3.2. Phân loại phân khúc giá (tập validation)

| Mô hình | Accuracy | Precision (macro) | Recall (macro) | F1 (macro) |
|---|---:|---:|---:|---:|
| **Baseline**: Dummy (lớp phổ biến) | 0,346 | 0,115 | 0,333 | 0,172 |
| Logistic Regression | 0,672 | 0,667 | 0,673 | 0,667 |
| Random Forest | 0,695 | 0,690 | 0,696 | 0,690 |
| **Extra Trees** ★ được chọn | **0,704** | **0,701** | **0,705** | **0,700** |

**Extra Trees trên tập test: Accuracy 73,5% · Precision 0,732 · Recall 0,735 · F1-macro 0,732.**

Ma trận nhầm lẫn (tập test; hàng là thực tế, cột là dự đoán):

| Thực tế \ Dự đoán | Thấp | Trung bình | Cao | Recall |
|---|---:|---:|---:|---:|
| **Thấp** | **303** | 66 | 17 | 78,5% |
| **Trung bình** | 76 | **225** | 76 | 59,7% |
| **Cao** | 17 | 48 | **304** | 82,4% |

### 3.3. Phân cụm K-Means

- **Đặc trưng:** log(giá), % giảm, rating, log(số lượt đánh giá), số danh mục; cùng danh mục, loại sản phẩm, nhà bán lẻ (one-hot, gom nhóm hiếm < 20).
- **Chuẩn hóa:** StandardScaler.
- **Chọn k:** thử k = 2…10, chọn theo **silhouette** (tính trên mẫu 3.000 điểm):

| k | 2 | 3 | 4 | 5 | 6 | **7** | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Silhouette | 0,210 | 0,232 | 0,250 | 0,274 | 0,273 | **0,285** | 0,277 | 0,272 | 0,222 |

- **k = 7** được chọn. Số sản phẩm mỗi cụm (cụm 0 → 6): 931 / 1.728 / 864 / 783 / 528 / 725 / 98. Trang **Phân khúc** hiển thị đặc điểm từng cụm (giá trung vị, mức giảm, rating, danh mục và nhà bán lẻ nổi bật).

### 3.4. Phát hiện bất thường — Isolation Forest

- **Đặc trưng:** log(giá), giá so với trung vị danh mục, % giảm, tỷ lệ niêm yết/bán, rating, log(số lượt đánh giá); điền trung vị + StandardScaler.
- **Kết quả:** với contamination 5% (300 cây), mô hình đánh dấu **283 / 5.657** sản phẩm (5,0%): Hasaki 254, Guardian 16, Thế Giới Skin Food 8, Cocolux 5. Phần lớn là hàng cận date / xả kho của Hasaki (giá bán rất thấp so với giá niêm yết).
- **Lý do bất thường:** mỗi sản phẩm được gắn 1–2 đặc trưng lệch nhiều nhất (|z| ≥ 1,5), ví dụ "Giá niêm yết cao bất thường; Giảm giá rất sâu".

Độ nhạy theo tham số contamination:

| Contamination | Số sản phẩm bị đánh dấu |
|---:|---:|
| 2% | 114 |
| **5%** (đang dùng) | **283** |
| 8% | 453 |

## 4. Giải thích kết quả

- **Thương hiệu là yếu tố quyết định giá:** chiếm 38% độ quan trọng ở mô hình hồi quy và 46% ở mô hình phân loại. Tiếp theo là **dung tích** (26% / 13%) và **danh mục** (12% / 16%). Kết quả này hợp lý: cùng một danh mục, giá chủ yếu khác nhau theo thương hiệu và quy cách.
- **Rating và số lượt đánh giá gần như không giúp dự đoán giá** (< 3%). Mức độ được đánh giá cao không gắn với giá đắt hay rẻ.
- **Hàng giá rẻ khó dự đoán theo tỷ lệ phần trăm** (sai số 55,8%): sai lệch 50k trên sản phẩm 80k đã là hơn 60%. Nhóm trung bình và cao chính xác hơn nhiều (khoảng 23–27%).
- **Phân loại nhầm chủ yếu giữa 2 nhóm cạnh nhau** (Thấp ↔ Trung bình, Trung bình ↔ Cao). Chỉ có 34/1.132 trường hợp nhầm Thấp ↔ Cao. Nhóm Trung bình khó nhất (recall 60%) vì nằm giữa 2 ngưỡng.
- **Silhouette khoảng 0,28 nghĩa là các cụm có chồng lấn:** thị trường mỹ phẩm không chia thành những nhóm tách bạch. Các cụm nên dùng để mô tả xu hướng, không phải ranh giới cứng.

## 5. Hạn chế

1. **Dữ liệu ngắn hạn:** dữ liệu gốc chỉ có 4 ngày thu thập (18–21/10/2026). Chưa đủ để mô hình hóa biến động giá theo thời gian hay theo mùa khuyến mãi. Công cụ thu thập (trang **Thu thập dữ liệu**, có lịch tự động) cho phép kéo dài lịch sử giá để huấn luyện lại sau.
2. **Thiếu đặc trưng quan trọng:** thành phần, công dụng, xuất xứ, kênh (chính hãng hay xách tay) không có trong dữ liệu. Dung tích/khối lượng trích từ tên sản phẩm: 6,2% sản phẩm không có cả hai, và cách trích bằng quy tắc có thể đọc nhầm với tên combo.
3. **Rating thiếu nhiều:** 65,5% sản phẩm không có rating (rating = 0 được coi là chưa có; Thế Giới Skin Food không công khai rating).
4. **Cùng một sản phẩm ở nhiều nhà bán lẻ chưa được đối chiếu** (`product_matching` mới là ứng viên). Sản phẩm trùng có thể nằm ở cả train lẫn test, làm kết quả hơi lạc quan.
5. **R² test (0,536) thấp hơn validation (0,601):** chênh lệch do chia ngẫu nhiên một lần trên dữ liệu không lớn; con số test là con số báo cáo chính thức.
6. **Isolation Forest chỉ ra sản phẩm "cần rà soát",** không khẳng định dữ liệu sai. Tỷ lệ 5% là giả định, không phải số đo.

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
  import numpy as np
  model = joblib.load("dataset/models/price_regressor.joblib")
  gia = np.exp(model.predict(df))   # mô hình dự đoán log(giá)
  ```
  Trong đó `df` có đúng các cột ở mục 2.
- **Xem kết quả trên website:** trang **Dự đoán giá**, **Phân khúc** và **Phát hiện bất thường**.
