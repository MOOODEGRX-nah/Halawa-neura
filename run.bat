@echo off
chcp 65001 >nul
title J.A.R.V.I.S

if not exist .venv\Scripts\activate.bat (
    echo لم يتم التثبيت بعد! شغل install.bat اولا
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python src\jarvis_launcher.py %*
if errorlevel 1 pause
