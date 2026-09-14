@echo off
chcp 65001 >nul
title JARVIS - Installer
echo ============================================
echo    JARVIS - تثبيت الاعتماديات
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo [خطأ] Python غير مثبت! ثبته من python.org مع خيار Add to PATH
    pause
    exit /b 1
)

if not exist .venv (
    echo [1/5] انشاء بيئة افتراضية...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [2/5] تحديث pip...
python -m pip install --upgrade pip

echo [3/5] تثبيت الحزم الاساسية...
pip install -r requirements.txt

echo [4/5] تثبيت محرك الذكاء llama.cpp...
pip install llama-cpp-python
if errorlevel 1 (
    echo [تنبيه] فشل تثبيت llama-cpp-python - سيعمل JARVIS بالوضع الاساسي
)

echo [5/5] تثبيت الصوت و GitHub (اختياري)...
pip install SpeechRecognition pyttsx3
pip install pyaudio
if errorlevel 1 (
    echo [تنبيه] تعذر تثبيت الصوت - الميزة لن تكون متاحة
)
pip install PyGithub

echo ============================================
echo    اكتمل التثبيت! شغل البرنامج عبر run.bat
echo ============================================
pause
