@echo off
REM Cai dat BeautyPrice Intelligence tren may moi (chua co Python).
REM   1. Tim Python 3.9+ ; chua co thi hoi truoc khi cai
REM   2. Tao moi truong ao .venv rieng cho du an
REM   3. Cai Flask tu libs\wheels (khong can mang) hoac tai ve neu thieu
REM   4. Mo website
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ==================================================================
echo  CAI DAT BEAUTYPRICE INTELLIGENCE
echo.
echo  Script nay se:
echo    1. Kiem tra Python 3.9 tro len
echo    2. Tao moi truong ao .venv rieng trong thu muc du an
echo    3. Cai Flask tu thu muc libs\wheels (khong can mang)
echo    4. Mo website tai http://127.0.0.1:5000/
echo.
echo  Khong co gi duoc cai ra ngoai thu muc du an, tru Python (neu thieu
echo  va ban dong y cai).
echo ==================================================================
echo.

REM ---------------------------------------------------------------- 1. Python
call :findpy
if defined PY goto :gotpy

echo [1/4] Khong tim thay Python 3.9 tro len tren may.
echo.
echo       Python la phan mem mien phi cua python.org, bat buoc phai co
echo       thi du an moi chay duoc.
echo.
set "ANS="
set /p "ANS=Cai Python ngay bay gio? (can mang) [Y/N]: "
if defined ANS set "ANS=!ANS:~0,1!"
if /i not "!ANS!"=="Y" (
    echo.
    echo Da huy. Ban co the tu cai Python roi chay lai cai-dat.bat:
    echo   - Tai tai https://www.python.org/downloads/
    echo   - Khi cai nho tick "Add python.exe to PATH"
    pause
    exit /b 1
)

echo.
echo       Dang thu cai bang winget (kho phan mem co san cua Windows)...
where winget >nul 2>nul
if errorlevel 1 goto :dltai
winget install --id Python.Python.3.12 -e --source winget --silent --accept-package-agreements --accept-source-agreements
call :findpy
if defined PY goto :gotpy

:dltai
echo       Khong dung duoc winget, chuyen sang tai tu python.org...
set "PYEXE=%TEMP%\python-3.12.10-amd64.exe"
curl -fL -o "%PYEXE%" "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
if errorlevel 1 goto :nopython
echo       Dang cai Python (chi cho tai khoan nay)...
"%PYEXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del /q "%PYEXE%" >nul 2>nul
call :findpy
if not defined PY goto :nopython

:gotpy
chcp 65001 >nul
echo.
echo [1/4] Python: %PY%
for /f "tokens=*" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do echo       Phien ban %%v

REM ---------------------------------------------------------------- 2. venv
cd /d "%~dp0source-code\backend"
REM cmd khong doi errorlevel khi chay duong dan trong nhay kep ma file khong co -> phai kiem tra exist truoc
set "VENVOK="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "pass" >nul 2>nul
    if not errorlevel 1 set "VENVOK=1"
)
if defined VENVOK (
    echo [2/4] Moi truong ao .venv da co, dung lai.
) else (
    if exist ".venv" (
        echo [2/4] Moi truong ao .venv cu khong dung duoc - dang tao lai ...
        rmdir /s /q ".venv"
    ) else (
        echo [2/4] Dang tao moi truong ao .venv ...
    )
    %PY% -m venv .venv
    if errorlevel 1 goto :venverr
)
set "VPY=.venv\Scripts\python.exe"

REM ---------------------------------------------------------------- 3. Flask
echo [3/4] Dang cai Flask ...
set "LIBOK="
if exist "%VPY%" (
    "%VPY%" -c "import flask, flask_cors" >nul 2>nul
    if not errorlevel 1 set "LIBOK=1"
)
if defined LIBOK (
    echo       Da co san, bo qua.
    goto :runit
)
"%VPY%" -m pip install --disable-pip-version-check -q --no-index --find-links "..\..\libs\wheels" -r requirements.txt
if not errorlevel 1 (
    echo       Da cai tu libs\wheels, khong can mang.
    goto :runit
)
echo       Thu muc libs\wheels khong du, chuyen sang tai tu mang...
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :piperr

:runit
REM ---------------------------------------------------------------- 4. chay
echo [4/4] Cai dat xong.
echo.
echo       Tai khoan: admin / Admin@123 (quan tri)  -  user / User@123 (chi xem)
echo       Lan sau chi can chay run.bat.
echo.
set "ANS="
set /p "ANS=Mo website ngay bay gio? [Y/N]: "
if defined ANS set "ANS=!ANS:~0,1!"
if /i "!ANS!"=="Y" (
    cd /d "%~dp0"
    call "%~dp0run.bat"
    exit /b
)
echo Khi can, chay run.bat de mo website.
pause
exit /b 0

REM ---------------------------------------------------------------- ham phu
:findpy
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
    exit /b
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PY=python"
    exit /b
)
REM Vua cai xong thi PATH cua cua so nay chua cap nhat -> tim trong thu muc mac dinh
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
)
if defined PY exit /b
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
)
exit /b

:nopython
echo.
echo Khong cai duoc Python tu dong.
echo Hay cai thu cong roi chay lai cai-dat.bat:
echo   1. Vao https://www.python.org/downloads/
echo   2. Tai ban moi nhat cho Windows va cai
echo   3. Khi cai NHO TICK "Add python.exe to PATH"
pause
exit /b 1

:venverr
echo.
echo Khong tao duoc moi truong ao. Thu go va cai lai Python.
pause
exit /b 1

:piperr
echo.
echo Khong cai duoc Flask. Kiem tra ket noi mang roi chay lai cai-dat.bat.
pause
exit /b 1
