@echo off
REM Chay BeautyPrice Intelligence tren Windows: tu tao moi truong ao, cai thu vien, mo trinh duyet.
chcp 65001 >nul
cd /d "%~dp0source-code\backend"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :nopython

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Tao moi truong ao .venv ...
    %PY% -m venv .venv || goto :nopython
)

echo [2/3] Cai thu vien (Flask, flask-cors) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :piperror

if defined BEAUTY_PORT (set "BEAUTY_PORT_OR_DEFAULT=%BEAUTY_PORT%") else (set "BEAUTY_PORT_OR_DEFAULT=5000")
echo [3/3] Khoi dong backend tai http://127.0.0.1:%BEAUTY_PORT_OR_DEFAULT%/  (Ctrl+C de dung)
echo       Neu chua co dataset\beautyprice.db, backend se tu dung CSDL tu dataset\raw.
if not "%BEAUTY_NO_BROWSER%"=="1" start "" cmd /c "ping -n 4 127.0.0.1 >nul & start http://127.0.0.1:%BEAUTY_PORT_OR_DEFAULT%/"
".venv\Scripts\python.exe" app.py
goto :eof

:nopython
echo Khong tim thay Python 3.9+. Cai tai https://www.python.org/downloads/ va tick "Add python.exe to PATH".
pause
exit /b 1

:piperror
echo Cai thu vien that bai. Kiem tra ket noi mang roi chay lai run.bat.
pause
exit /b 1
