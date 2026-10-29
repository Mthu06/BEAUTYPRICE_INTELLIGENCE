@echo off
REM Chay BeautyPrice Intelligence tren Windows: tu tao moi truong ao, cai thu vien, mo trinh duyet.
chcp 65001 >nul
REM Tat server cu (neu con chay) truoc: Windows cho phep 2 server cung mo 1 cong -> trang luc goi ban moi, luc goi ban cu.
call "%~dp0stop.bat"
cd /d "%~dp0source-code\backend"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :nopython

REM cmd khong doi errorlevel khi chay duong dan trong nhay kep ma file khong co -> phai kiem tra exist truoc
set "VENVOK="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "pass" >nul 2>nul
    if not errorlevel 1 set "VENVOK=1"
)
if defined VENVOK goto :venvok
if exist ".venv" (
    echo [1/3] Moi truong ao .venv khong dung duoc ^(Python goc da bi go hoac doi cho^) - dang tao lai ...
    rmdir /s /q ".venv"
) else (
    echo [1/3] Tao moi truong ao .venv ...
)
%PY% -m venv .venv || goto :venverror
:venvok

echo [2/3] Cai thu vien (Flask, flask-cors) ...
".venv\Scripts\python.exe" -c "import flask, flask_cors" >nul 2>nul
if not errorlevel 1 goto :libok
REM Uu tien cai tu libs\wheels (khong can mang), khong duoc thi tai tu mang
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --no-index --find-links "..\..\libs\wheels" -r requirements.txt
if not errorlevel 1 goto :libok
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :piperror
:libok

if defined BEAUTY_PORT (set "BEAUTY_PORT_OR_DEFAULT=%BEAUTY_PORT%") else (set "BEAUTY_PORT_OR_DEFAULT=5000")
echo [3/3] Khoi dong backend tai http://127.0.0.1:%BEAUTY_PORT_OR_DEFAULT%/  (Ctrl+C de dung)
echo       Neu chua co dataset\beautyprice.db, backend se tu dung CSDL tu dataset\raw.
if not "%BEAUTY_NO_BROWSER%"=="1" start "" cmd /c "ping -n 4 127.0.0.1 >nul & start http://127.0.0.1:%BEAUTY_PORT_OR_DEFAULT%/"
".venv\Scripts\python.exe" app.py || pause
goto :eof

:nopython
echo Khong tim thay Python 3.9+.
echo Chay cai-dat.bat de script tu cai Python va thu vien giup ban,
echo hoac tai tai https://www.python.org/downloads/ va tick "Add python.exe to PATH".
pause
exit /b 1

:venverror
echo Khong tao duoc moi truong ao .venv. Thu chay cai-dat.bat, hoac go va cai lai Python.
pause
exit /b 1

:piperror
echo Cai thu vien that bai. Kiem tra ket noi mang roi chay lai run.bat.
pause
exit /b 1
