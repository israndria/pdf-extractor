@echo off
title V25 PDF Extractor — MinerU
cd /d "%~dp0"

echo ============================================
echo  V25 PDF Extractor ^| MinerU 3.0.8
echo  Streamlit port: 8508
echo ============================================
echo.

REM Tambahkan Java ke PATH (untuk kompabilitas tool lama)
set "JAVA_BIN=D:\Temurin\bin"
if exist "%JAVA_BIN%\java.exe" (
    set "PATH=%JAVA_BIN%;%PATH%"
    echo [OK] Java ditemukan: %JAVA_BIN%
) else (
    echo [INFO] Java tidak ditemukan, dilanjutkan tanpa Java
)

REM Cek venv Python 3.12
set "VENV_PYTHON=%~dp0venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment tidak ditemukan!
    echo Jalankan setup:
    echo   py -3.12 -m venv venv
    echo   venv\Scripts\pip install uv
    echo   venv\Scripts\uv pip install mineru[core] streamlit supabase
    pause
    exit /b 1
)

echo [OK] Python venv: %VENV_PYTHON%
echo.
echo Membuka browser di http://localhost:8507 ...
echo Tekan Ctrl+C di jendela ini untuk menghentikan server.
echo.

"%VENV_PYTHON%" -m streamlit run "%~dp0app.py" --server.port 8508 --server.headless false --browser.gatherUsageStats false
pause
