# Tài liệu tham khảo và lưu trữ

## Lưu trữ trong thư mục này

- `ml_ket_qua_goc/`: kết quả mô hình **bản trước**, do notebook cũ tạo ra (CSV, JSON, joblib). Code huấn luyện của bản này không còn. Hiện nay mô hình được tái tạo bằng `source-code/pipeline/train_models.py`, và website đọc kết quả từ CSDL. Thư mục này chỉ giữ lại để đối chiếu.
- `_luu_tru/`: file trùng lặp của cấu trúc cũ, đã kiểm tra mã băm trùng với dữ liệu hiện tại:
  - `gđ6cc.zip`
  - `backend_cu/` (CSV, `products_working.json`, `ML.zip`)

  Thư mục này **có thể xóa** trước khi nộp để giảm dung lượng.

Trên git **không** đưa lên `refs/_luu_tru/` (bản trùng) và `refs/ml_ket_qua_goc/*.joblib` (mô hình cũ, khoảng 43 MB). Mô hình hiện dùng nằm ở `dataset/models/` và tạo lại được bằng `source-code/pipeline/train_models.py`.

## Tài liệu tham khảo (nhóm bổ sung)

- Tài liệu scikit-learn: https://scikit-learn.org/stable/
- Tài liệu Flask: https://flask.palletsprojects.com/
- Tài liệu SQLite: https://www.sqlite.org/docs.html
- Tài liệu Chart.js: https://www.chartjs.org/docs/4.4.1/
- Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). *Isolation Forest*. ICDM.
- Rousseeuw, P. J. (1987). *Silhouettes: a graphical aid to the interpretation and validation of cluster analysis*.
