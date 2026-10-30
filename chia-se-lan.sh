#!/usr/bin/env bash
# Chia sẻ website cho các máy khác trong cùng mạng LAN.
# Máy này làm server, các máy khác chỉ cần mở trình duyệt.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${BEAUTY_PORT:-5000}"

cat <<'BANNER'
==================================================================
 CHIA SẺ WEBSITE TRONG MẠNG LAN

 Máy này làm server. Các máy khác cùng mạng WiFi / dây mạng
 chỉ cần mở trình duyệt, không cần cài gì.

 Lưu ý: chỉ mở trong mạng nội bộ, KHÔNG mở ra Internet.
 Mọi người dùng chung 1 CSDL trên máy này, nên ai sửa thì
 máy khác cũng thấy.
==================================================================
BANNER

# Địa chỉ IP trong mạng LAN
LANIP=""
if command -v ipconfig >/dev/null 2>&1; then
    LANIP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
fi
if [ -z "$LANIP" ] && command -v ip >/dev/null 2>&1; then
    LANIP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '/src/ {print $7; exit}')
fi
if [ -z "$LANIP" ] && command -v hostname >/dev/null 2>&1; then
    LANIP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

if [ -z "$LANIP" ]; then
    echo "Không tìm được địa chỉ IP trong mạng LAN. Hãy kiểm tra kết nối mạng."
    exit 1
fi

echo
echo "Địa chỉ để các máy khác truy cập:"
echo
echo "       http://$LANIP:$PORT/"
echo
echo "Nếu máy khác không vào được, kiểm tra tường lửa của hệ điều hành"
echo "cho phép kết nối đến cổng $PORT."
echo
echo "Tài khoản: admin / Admin@123 (quản trị)  -  user / User@123 (chỉ xem)"
echo

export BEAUTY_HOST=0.0.0.0
exec bash "$DIR/run.sh"
