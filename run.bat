@echo off
chcp 65001 >nul
title Neura

set PYDIR=%~dp0python-embed

if not exist "%PYDIR%\python.exe" (
    echo أول تشغيل: جاري تجهيز المتطلبات تلقائياً...
    call "%~dp0install.bat"
)

"%PYDIR%\python.exe" "%~dp0src\neura_launcher.py" %*
if errorlevel 1 pause
