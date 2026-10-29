#!/usr/bin/env bash
# Cài đặt BeautyPrice Intelligence trên máy mới (macOS / Linux).
#   1. Tìm Python 3.9+  2. Tạo .venv  3. Cài Flask (ưu tiên libs/wheels)  4. Mở website
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

cat <<'BANNER'
==================================================================
 CÀI ĐẶT BEAUTYPRICE INTELLIGENCE

 Script này sẽ:
   1. Kiểm tra Python 3.9 trở lên
   2. Tạo môi trường ảo .venv riêng trong thư mục dự án
   3. Cài Flask (ưu tiên lấy từ libs/wheels, không cần mạng)
   4. Mở website tại http://127.0.0.1:5000/
==================================================================
BANNER

PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" 2>/dev/null; then
        PY="$c"; break
    fi
done

if [ -z "$PY" ]; then
    echo
    echo "[1/4] Không tìm thấy Python 3.9 trở lên."
    echo "      Hãy cài Python rồi chạy lại ./cai-dat.sh:"
    echo "        macOS:          brew install python3"
    echo "        Ubuntu/Debian:  sudo apt install python3 python3-venv python3-pip"
    echo "        Hoặc tải tại:   https://www.python.org/downloads/"
    exit 1
fi
echo
echo "[1/4] Python: $($PY -c 'import sys; print(sys.executable, sys.version.split()[0])')"

cd "$DIR/source-code/backend"
if .venv/bin/python -c "pass" >/dev/null 2>&1; then
    echo "[2/4] Môi trường ảo .venv đã có, dùng lại."
else
    if [ -d .venv ]; then
        echo "[2/4] Môi trường ảo .venv cũ không dùng được - đang tạo lại ..."
        rm -rf .venv
    else
        echo "[2/4] Đang tạo môi trường ảo .venv ..."
    fi
    "$PY" -m venv .venv
fi
VPY=.venv/bin/python

echo "[3/4] Đang cài Flask ..."
if "$VPY" -c "import flask, flask_cors" >/dev/null 2>&1; then
    echo "      Đã có sẵn, bỏ qua."
elif "$VPY" -m pip install --disable-pip-version-check -q --no-index --find-links "$DIR/libs/wheels" -r requirements.txt 2>/dev/null; then
    echo "      Đã cài từ libs/wheels, không cần mạng."
else
    echo "      Thư mục libs/wheels không đủ cho hệ điều hành này, chuyển sang tải từ mạng..."
    "$VPY" -m pip install --disable-pip-version-check -q -r requirements.txt
fi

echo "[4/4] Cài đặt xong."
echo
echo "      Tài khoản: admin / Admin@123 (quản trị)  -  user / User@123 (chỉ xem)"
echo "      Lần sau chỉ cần chạy ./run.sh"
echo
read -r -p "Mở website ngay bây giờ? [Y/N]: " ANS
case "$ANS" in
    [Yy]*) exec bash "$DIR/run.sh" ;;
    *) echo "Khi cần, chạy ./run.sh để mở website." ;;
esac
