@echo off
REM Khoi phuc CSDL ve dung du lieu goc trong dataset\raw.
REM CSDL hien tai duoc giu lai thanh dataset\beautyprice.(thoi diem).bak truoc khi dung lai.
setlocal

echo ==================================================================
echo  KHOI PHUC DU LIEU GOC
echo.
echo  Dung lai dataset\beautyprice.db tu dataset\raw:
echo    5.657 san pham - 6.350 snapshot gia - 6.673 review
echo.
echo  CAC THAY DOI SAU SE BI BO:
echo    - san pham da them / sua / xoa tren web
echo    - gia va review da thu thap them
echo    - lich thu thap tu dong (ban sao luu khong bi anh huong)
echo  CSDL hien tai duoc giu lai thanh dataset\beautyprice.(thoi diem).bak
echo ==================================================================
echo.
set "OK="
set /p "OK=Go Y roi Enter de khoi phuc (phim khac de huy): "
REM chi lay ky tu dau de bo ky tu thua khi dau vao co dang Windows
if defined OK set "OK=%OK:~0,1%"
if /i not "%OK%"=="Y" (
    echo Da huy, khong thay doi gi.
    goto :eof
)

cd /d "%~dp0source-code\backend"
if not exist ".venv\Scripts\python.exe" (
    echo Chua co moi truong ao .venv. Hay chay run.bat it nhat 1 lan truoc.
    pause
    exit /b 1
)

REM Hoi truoc ve mo hinh hoc may de khong phai cho giua chung
set "HAVEML=0"
".venv\Scripts\python.exe" -c "import sklearn" >nul 2>nul
if not errorlevel 1 set "HAVEML=1"
set "ANSML=N"
if "%HAVEML%"=="1" set "ANSML=Y"
if "%HAVEML%"=="0" echo.
if "%HAVEML%"=="0" echo Chua cai thu vien hoc may (scikit-learn, pandas, numpy, joblib).
if "%HAVEML%"=="0" echo Neu bo qua, 3 trang Phan khuc / Du doan gia / Phat hien bat thuong se trong.
if "%HAVEML%"=="0" set /p "ANSML=Cai va huan luyen lai luon? (khoang 100 MB, can mang) [Y/N]: "
if defined ANSML set "ANSML=%ANSML:~0,1%"

chcp 65001 >nul
call "%~dp0stop.bat"

echo.
echo [1/2] Dung lai CSDL tu dataset\raw ...
".venv\Scripts\python.exe" "..\pipeline\build_database.py" --force || goto :err

echo.
echo [2/2] Ket qua mo hinh hoc may ...
if /i not "%ANSML%"=="Y" goto :skipml
if "%HAVEML%"=="0" ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r "..\pipeline\requirements-ml.txt" || goto :err
".venv\Scripts\python.exe" "..\pipeline\train_models.py" || goto :err
goto :done

:skipml
echo    Da bo qua. Khi can ket qua mo hinh, chay 2 lenh sau tu thu muc du an:
echo      source-code\backend\.venv\Scripts\python.exe -m pip install -r source-code\pipeline\requirements-ml.txt
echo      source-code\backend\.venv\Scripts\python.exe source-code\pipeline\train_models.py

:done
echo.
echo Xong. Chay run.bat de mo lai website.
pause
goto :eof

:err
echo.
echo Co loi xay ra. CSDL cu van con trong thu muc dataset (duoi dang .bak).
pause
exit /b 1
