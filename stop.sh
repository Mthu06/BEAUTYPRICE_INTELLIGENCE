#!/usr/bin/env bash
# Tắt server BeautyPrice Intelligence đang chạy (mặc định cổng 5000, đổi bằng biến BEAUTY_PORT).
# Chỉ tắt tiến trình python đang nghe cổng đó, không đụng ứng dụng khác.
PORT="${BEAUTY_PORT:-5000}"
PIDS=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | sort -u)
FOUND=0
for pid in $PIDS; do
    name=$(ps -p "$pid" -o comm= 2>/dev/null)
    case "$name" in
        *python*) echo "Đang tắt server (PID $pid) tại cổng $PORT ..."; kill "$pid" && FOUND=1 ;;
        *) echo "Cổng $PORT đang dùng bởi $name (PID $pid), không phải server của dự án - bỏ qua." ;;
    esac
done
[ "$FOUND" = 1 ] && echo "Đã tắt server." || echo "Không có server BeautyPrice nào đang chạy tại cổng $PORT."
