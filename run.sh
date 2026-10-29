#!/usr/bin/env bash
# Chạy BeautyPrice Intelligence trên macOS/Linux: tự tạo môi trường ảo, cài thư viện, mở trình duyệt.
set -e
# Tắt server cũ (nếu còn chạy) trước, để luôn chạy đúng bản code mới nhất
bash "$(dirname "$0")/stop.sh" || true
cd "$(dirname "$0")/source-code/backend"

PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
    echo "Không tìm thấy Python 3.9+. Hãy cài Python rồi chạy lại." >&2
    exit 1
fi

if ! .venv/bin/python -c "pass" >/dev/null 2>&1; then
    if [ -d .venv ]; then
        echo "[1/3] Môi trường ảo .venv không dùng được (Python gốc đã bị gỡ hoặc đổi chỗ) - đang tạo lại ..."
        rm -rf .venv
    else
        echo "[1/3] Tạo môi trường ảo .venv ..."
    fi
    "$PY" -m venv .venv
fi

echo "[2/3] Cài thư viện (Flask, flask-cors) ..."
if ! .venv/bin/python -c "import flask, flask_cors" >/dev/null 2>&1; then
    # Ưu tiên cài từ libs/wheels (không cần mạng), không được thì tải từ mạng
    .venv/bin/python -m pip install --disable-pip-version-check -q --no-index --find-links ../../libs/wheels -r requirements.txt 2>/dev/null \
        || .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
fi

URL="http://127.0.0.1:${BEAUTY_PORT:-5000}/"
echo "[3/3] Khởi động backend tại $URL (Ctrl+C để dừng)"
[ "${BEAUTY_NO_BROWSER:-0}" = "1" ] || ( sleep 3; (command -v xdg-open >/dev/null && xdg-open "$URL") || (command -v open >/dev/null && open "$URL") ) >/dev/null 2>&1 &
exec .venv/bin/python app.py
