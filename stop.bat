@echo off
REM Tat server BeautyPrice Intelligence dang chay (mac dinh cong 5000, doi bang bien BEAUTY_PORT).
REM Chi tat tien trinh python dang nghe cong do, khong dong ung dung khac.
setlocal EnableDelayedExpansion
chcp 65001 >nul
if defined BEAUTY_PORT (set "PORT=%BEAUTY_PORT%") else (set "PORT=5000")
set "FOUND="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
    if not "%%p"=="0" if not defined SEEN_%%p (
        set "SEEN_%%p=1"
        set "NAME="
        for /f "tokens=1 delims=," %%n in ('tasklist /fi "PID eq %%p" /fo csv /nh') do set "NAME=%%~n"
        echo !NAME! | findstr /i /b "python" >nul
        if not errorlevel 1 (
            echo Dang tat server ^(PID %%p^) tai cong %PORT% ...
            taskkill /PID %%p /T /F >nul 2>nul && set "FOUND=1"
        ) else (
            echo Cong %PORT% dang dung boi !NAME! ^(PID %%p^), khong phai server cua du an - bo qua.
        )
    )
)
if defined FOUND (
    echo Da tat server.
) else (
    echo Khong co server BeautyPrice nao dang chay tai cong %PORT%.
)
endlocal
