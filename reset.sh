#!/usr/bin/env bash
# Khôi phục CSDL về đúng dữ liệu gốc trong dataset/raw.
# CSDL hiện tại được giữ lại thành dataset/beautyprice.<thời điểm>.bak trước khi dựng lại.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

cat <<'BANNER'
==================================================================
 KHÔI PHỤC DỮ LIỆU GỐC

 Dựng lại dataset/beautyprice.db từ dataset/raw:
   5.657 sản phẩm - 6.350 snapshot giá - 6.673 review

 CÁC THAY ĐỔI SAU SẼ BỊ BỎ:
   - sản phẩm đã thêm / sửa / xóa trên web
   - giá và review đã thu thập thêm
   - lịch thu thập tự động; bản sao lưu không bị ảnh hưởng
 CSDL hiện tại được giữ lại thành dataset/beautyprice.<thời điểm>.bak
==================================================================
BANNER

read -r -p "Gõ Y rồi Enter để khôi phục (phím khác để hủy): " OK
case "$OK" in
    [Yy]) ;;
    *) echo "Đã hủy, không thay đổi gì."; exit 0 ;;
esac

bash "$DIR/stop.sh" || true

cd "$DIR/source-code/backend"
if [ ! -x .venv/bin/python ]; then
    echo "Chưa có môi trường ảo .venv. Hãy chạy ./run.sh ít nhất 1 lần trước." >&2
    exit 1
fi
PY=.venv/bin/python

echo
echo "[1/2] Dựng lại CSDL từ dataset/raw ..."
"$PY" ../pipeline/build_database.py --force

echo
echo "[2/2] Kết quả mô hình học máy ..."
if ! "$PY" -c "import sklearn" >/dev/null 2>&1; then
    echo "   Chưa cài thư viện học máy (scikit-learn, pandas, numpy, joblib)."
    echo "   Nếu bỏ qua, 3 trang Phân khúc / Dự đoán giá / Phát hiện bất thường sẽ trống."
    read -r -p "Cài và huấn luyện lại ngay bây giờ? (khoảng 100 MB, cần mạng) [Y/N]: " ML
    case "$ML" in
        [Yy]) "$PY" -m pip install --disable-pip-version-check -q -r ../pipeline/requirements-ml.txt ;;
        *)
            echo "   Đã bỏ qua. Khi cần kết quả mô hình, chạy 2 lệnh sau từ thư mục dự án:"
            echo "     source-code/backend/.venv/bin/python -m pip install -r source-code/pipeline/requirements-ml.txt"
            echo "     source-code/backend/.venv/bin/python source-code/pipeline/train_models.py"
            echo
            echo "Xong. Chạy ./run.sh để mở lại website."
            exit 0 ;;
    esac
fi
"$PY" ../pipeline/train_models.py

echo
echo "Xong. Chạy ./run.sh để mở lại website."
