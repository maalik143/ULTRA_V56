@echo off
title ULTRA V5.6 ENTERPRISE ENGINE
cd /d "%~dp0"

echo.
echo ============================================================
echo   ULTRA V5.6 ENTERPRISE ENGINE -- Starting...
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating Python virtual environment...
    python -m venv .venv
    echo [*] Installing dependencies...
    .venv\Scripts\pip install -r requirements.txt
)

.venv\Scripts\python.exe -c "import loguru" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing core packages...
    .venv\Scripts\pip install loguru fastapi uvicorn httpx pydantic loguru
)

echo [*] Opening Dashboard in browser: http://localhost:8000
start "" "http://localhost:8000"

echo.
echo ============================================================
echo   SERVER IS LIVE AT http://localhost:8000
echo   Keep this window OPEN while using the application.
echo ============================================================
echo.

.venv\Scripts\python.exe -m backend.main

echo.
if errorlevel 1 (
    echo [!] Server exited with an error. Check logs above.
) else (
    echo [*] Server stopped cleanly.
)
echo.
pause
