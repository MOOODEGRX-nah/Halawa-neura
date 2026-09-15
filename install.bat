@echo off
chcp 65001 >nul
title Neura - Installer
setlocal

set PYDIR=%~dp0python-embed
set PYZIP=%~dp0python-embed.zip
set PYURL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip
set GETPIP=https://bootstrap.pypa.io/get-pip.py

if not exist "%PYDIR%\python.exe" (
    echo [1/4] تحميل Python المدمج...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYZIP%'"
    powershell -Command "Expand-Archive -Path '%PYZIP%' -DestinationPath '%PYDIR%' -Force"
    del "%PYZIP%"

    echo [2/4] تفعيل site-packages...
    powershell -Command "(Get-Content '%PYDIR%\python311._pth') -replace '#import site','import site' | Set-Content '%PYDIR%\python311._pth'"

    echo [3/4] تثبيت pip...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%GETPIP%' -OutFile '%PYDIR%\get-pip.py'"
    "%PYDIR%\python.exe" "%PYDIR%\get-pip.py" --no-warn-script-location
) else (
    echo [1/4] Python المدمج موجود - تخطي التحميل.
)

echo [4/4] تثبيت المكتبات...
"%PYDIR%\python.exe" -m pip install --upgrade pip --no-warn-script-location
"%PYDIR%\python.exe" -m pip install -r "%~dp0requirements.txt" --no-warn-script-location
"%PYDIR%\python.exe" -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/vulkan --no-warn-script-location
"%PYDIR%\python.exe" -m pip install SpeechRecognition pyttsx3 --no-warn-script-location
"%PYDIR%\python.exe" -m pip install PyGithub --no-warn-script-location

echo.
echo ============================================
echo    اكتمل التثبيت! شغل run.bat الآن
echo ============================================
pause
