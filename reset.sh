#!/usr/bin/env bash
# Khôi phục CSDL về đúng dữ liệu gốc.
# Cách 1 (ưu tiên): lấy lại bản trong git - có sẵn kết quả mô hình, không cần cài thêm gì.
# Cách 2 (dự phòng): dựng lại từ dataset/raw bằng build_database.py.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

cat <<'BANNER'
==================================================================
 KHÔI PHỤC DỮ LIỆU GỐC

 Đưa dataset/beautyprice.db về dữ liệu gốc:
   5.657 sản phẩm - 6.350 snapshot giá - 6.673 review

 CÁC THAY ĐỔI SAU SẼ BỊ BỎ:
   - sản phẩm đã thêm / sửa / xóa trên web
   - giá và review đã thu thập thêm
   - lịch thu thập tự động (bản sao lưu không bị ảnh hưởng)
 CSDL hiện tại được chép ra dataset/beautyprice.truoc-khoi-phuc.bak
==================================================================
BANNER

read -r -p "Gõ Y rồi Enter để khôi phục (phím khác để hủy): " OK
case "$OK" in
    [Yy]*) ;;
    *) echo "Đã hủy, không thay đổi gì."; exit 0 ;;
esac

bash "$DIR/stop.sh" || true
cd "$DIR"

if [ -f dataset/beautyprice.db ]; then
    cp -f dataset/beautyprice.db dataset/beautyprice.truoc-khoi-phuc.bak
    echo
    echo "Đã chép CSDL hiện tại ra dataset/beautyprice.truoc-khoi-phuc.bak"
fi

# ---- Cách 1: lấy lại bản gốc trong git (kèm kết quả mô hình) ----
if command -v git >/dev/null 2>&1 \
   && git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
   && git ls-files --error-unmatch dataset/beautyprice.db >/dev/null 2>&1 \
   && git checkout -- dataset/beautyprice.db; then
    echo
    echo "Xong: đã khôi phục CSDL gốc (có sẵn kết quả mô hình học máy)."
    echo "Chạy ./run.sh để mở lại website."
    exit 0
fi

# ---- Cách 2: dựng lại từ dataset/raw ----
echo
echo "Không lấy được từ git, chuyển sang dựng lại từ dataset/raw ..."
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
    echo "Chưa cài thư viện học máy. Đang thử cài bản dựng sẵn (không biên dịch) ..."
    if ! "$PY" -m pip install --disable-pip-version-check -q --only-binary=:all: -r ../pipeline/requirements-ml.txt; then
        echo
        echo "Không cài được thư viện học máy cho phiên bản Python này:"
        "$PY" -c "import sys; print('   Python đang dùng:', sys.version.split()[0])"
        echo "   3 trang Phân khúc / Dự đoán giá / Phát hiện bất thường sẽ trống."
        echo "   Cách đơn giản nhất: tải lại dự án bằng 'git clone' rồi chạy ./reset.sh,"
        echo "   script sẽ lấy thẳng CSDL gốc (đã có sẵn kết quả mô hình)."
        echo
        echo "Xong. Chạy ./run.sh để mở lại website."
        exit 0
    fi
fi
"$PY" ../pipeline/train_models.py

echo
echo "Xong. Chạy ./run.sh để mở lại website."
