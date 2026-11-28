@echo off
title OMZU
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo.
echo   OMZU ishga tushmoqda...  Brauzer avtomatik ochiladi.
echo   Yopish uchun shu oynani yoping.
echo.
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uzllm.server
pause
