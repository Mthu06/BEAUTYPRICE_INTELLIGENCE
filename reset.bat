@echo off
REM Khoi phuc CSDL ve dung du lieu goc.
REM Cach 1 (uu tien): lay lai ban trong git - co san ket qua mo hinh, khong can cai them gi.
REM Cach 2 (du phong): dung lai tu dataset\raw bang build_database.py.
setlocal

echo ==================================================================
echo  KHOI PHUC DU LIEU GOC
echo.
echo  Dua dataset\beautyprice.db ve du lieu goc:
echo    5.657 san pham - 6.350 snapshot gia - 6.673 review
echo.
echo  CAC THAY DOI SAU SE BI BO:
echo    - san pham da them / sua / xoa tren web
echo    - gia va review da thu thap them
echo    - lich thu thap tu dong (ban sao luu khong bi anh huong)
echo  CSDL hien tai duoc chep ra dataset\beautyprice.truoc-khoi-phuc.bak
echo ==================================================================
echo.
set "OK="
set /p "OK=Go Y roi Enter de khoi phuc (phim khac de huy): "
if defined OK set "OK=%OK:~0,1%"
if /i not "%OK%"=="Y" (
    echo Da huy, khong thay doi gi.
    goto :eof
)

chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0stop.bat"

if exist "dataset\beautyprice.db" (
    copy /y "dataset\beautyprice.db" "dataset\beautyprice.truoc-khoi-phuc.bak" >nul
    echo.
    echo Da chep CSDL hien tai ra dataset\beautyprice.truoc-khoi-phuc.bak
)

REM ---- Cach 1: lay lai ban goc trong git (kem ket qua mo hinh) ----
where git >nul 2>nul
if errorlevel 1 goto :rebuild
git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 goto :rebuild
git ls-files --error-unmatch "dataset/beautyprice.db" >nul 2>nul
if errorlevel 1 goto :rebuild
echo.
echo Dang lay lai CSDL goc tu git ...
git checkout -- "dataset/beautyprice.db"
if errorlevel 1 goto :rebuild
echo Xong: da khoi phuc CSDL goc (co san ket qua mo hinh hoc may).
goto :done

REM ---- Cach 2: dung lai tu dataset\raw ----
:rebuild
echo.
echo Khong lay duoc tu git, chuyen sang dung lai tu dataset\raw ...
cd /d "%~dp0source-code\backend"
if not exist ".venv\Scripts\python.exe" (
    echo Chua co moi truong ao .venv. Hay chay run.bat it nhat 1 lan truoc.
    pause
    exit /b 1
)
echo.
echo [1/2] Dung lai CSDL tu dataset\raw ...
".venv\Scripts\python.exe" "..\pipeline\build_database.py" --force || goto :err

echo.
echo [2/2] Ket qua mo hinh hoc may ...
".venv\Scripts\python.exe" -c "import sklearn" >nul 2>nul
if not errorlevel 1 goto :train

echo Chua cai thu vien hoc may. Dang thu cai ban dung san (khong bien dich) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --only-binary=:all: -r "..\pipeline\requirements-ml.txt"
if errorlevel 1 goto :noml

:train
".venv\Scripts\python.exe" "..\pipeline\train_models.py" || goto :err
goto :done

:noml
echo.
echo Khong cai duoc thu vien hoc may cho phien ban Python nay:
".venv\Scripts\python.exe" -c "import sys; print('   Python dang dung:', sys.version.split()[0])"
echo    3 trang Phan khuc / Du doan gia / Phat hien bat thuong se trong.
echo    Cach don gian nhat: tai lai du an bang "git clone" roi chay reset.bat,
echo    script se lay thang CSDL goc (da co san ket qua mo hinh).
echo    Hoac cai Python 3.11 / 3.12 tu python.org roi xoa thu muc
echo    source-code\backend\.venv va chay lai run.bat.

:done
echo.
echo Xong. Chay run.bat de mo lai website.
pause
goto :eof

:err
echo.
echo Co loi xay ra. CSDL truoc do van con o dataset\beautyprice.truoc-khoi-phuc.bak
pause
exit /b 1
