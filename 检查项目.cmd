@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
python -B scripts\verify.py %*
set "CHECK_EXIT=%ERRORLEVEL%"
pause
exit /b %CHECK_EXIT%
