#!/usr/bin/env bash
# Tắt server đang chạy (nếu có) rồi khởi động lại bằng run.sh - dùng sau khi cập nhật code.
DIR="$(dirname "$0")"
bash "$DIR/stop.sh"
sleep 1
exec bash "$DIR/run.sh"
