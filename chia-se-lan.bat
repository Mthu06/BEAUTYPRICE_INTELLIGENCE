@echo off
REM Chia se website cho cac may khac trong cung mang LAN (WiFi/day mang).
REM May nay lam server, giu nguyen du lieu; cac may khac chi mo trinh duyet.
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if defined BEAUTY_PORT (set "PORT=%BEAUTY_PORT%") else (set "PORT=5000")

echo ==================================================================
echo  CHIA SE WEBSITE TRONG MANG LAN
echo.
echo  May nay lam server. Cac may khac cung mang WiFi / day mang
echo  chi can mo trinh duyet, khong can cai gi.
echo.
echo  Luu y: chi mo trong mang noi bo, KHONG mo ra Internet.
echo  Moi nguoi deu dung chung 1 CSDL tren may nay, nen ai sua thi
echo  may khac cung thay.
echo ==================================================================
echo.

REM ---------------------------------------------------------------- IP mang LAN
set "LANIP="
REM Cach 1: PowerShell - IP cua card mang co duong ra ngoai (khong dung dau ong de batch khong hieu nham)
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "foreach($c in Get-NetIPConfiguration){ if($c.IPv4DefaultGateway -ne $null -and $c.NetAdapter.Status -eq 'Up'){ $c.IPv4Address.IPAddress; break } }" 2^>nul`) do if not defined LANIP set "LANIP=%%i"
REM Cach 2 (du phong): doc tu ipconfig
if not defined LANIP (
    for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /r /c:"IPv4.*: 19[02]\." /c:"IPv4.*: 10\."') do if not defined LANIP set "LANIP=%%i"
    if defined LANIP set "LANIP=!LANIP: =!"
)
if not defined LANIP (
    echo Khong tim duoc dia chi IP trong mang LAN.
    echo Hay kiem tra may da noi WiFi hoac day mang chua.
    pause
    exit /b 1
)

echo Dia chi de cac may khac truy cap:
echo.
echo        http://!LANIP!:%PORT%/
echo.

REM ---------------------------------------------------------------- tuong lua
netsh advfirewall firewall show rule name="BeautyPrice Intelligence" >nul 2>nul
if not errorlevel 1 (
    echo Tuong lua: da co san luat cho cong %PORT%.
    goto :start
)
net session >nul 2>nul
if errorlevel 1 goto :noadmin

echo Tuong lua Windows dang chan ket noi tu may khac.
set "ANS="
set /p "ANS=Them luat cho phep cong %PORT% trong mang noi bo? [Y/N]: "
if defined ANS set "ANS=!ANS:~0,1!"
if /i not "!ANS!"=="Y" goto :start
netsh advfirewall firewall add rule name="BeautyPrice Intelligence" dir=in action=allow protocol=TCP localport=%PORT% profile=private,domain >nul
if errorlevel 1 (
    echo    Khong them duoc luat. May khac co the khong vao duoc.
) else (
    echo    Da them luat ^(chi ap dung cho mang rieng, khong ap dung mang cong cong^).
    echo    Khi khong can nua, go bang lenh:
    echo      netsh advfirewall firewall delete rule name="BeautyPrice Intelligence"
)
goto :start

:noadmin
echo Tuong lua Windows co the chan ket noi tu may khac.
echo Neu may khac khong vao duoc, hay bam chuot phai vao chia-se-lan.bat
echo va chon "Run as administrator" de script tu them luat tuong lua.
echo.
echo Hoac khi Windows hien hop thoai hoi quyen cho Python, chon "Allow access"
echo va nho tick o "Private networks".
echo.

:start
chcp 65001 >nul
echo.
echo Dang khoi dong server... (Ctrl+C de dung)
echo Tai khoan: admin / Admin@123 (quan tri)  -  user / User@123 (chi xem)
echo.
set "BEAUTY_HOST=0.0.0.0"
call "%~dp0run.bat"
