@echo off
REM Tat server dang chay (neu co) roi khoi dong lai bang run.bat - dung sau khi cap nhat code.
chcp 65001 >nul
call "%~dp0stop.bat"
ping -n 2 127.0.0.1 >nul
call "%~dp0run.bat"
