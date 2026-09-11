@echo off
title Packing Slip Chef System
cd /d "%~dp0"

echo ==========================================
echo   Packing Slip Chef System
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PY=python
    ) else (
        echo Python is not installed.
        echo.
        echo Install Python 3.11 or newer from:
        echo https://www.python.org/downloads/
        echo.
        echo IMPORTANT: tick "Add Python to PATH" during installation.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating app environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :error
)

echo Installing required components...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Starting Packing Slip Chef System...
echo.
echo The app address is:
echo http://localhost:8501
echo.
echo Your browser will be opened automatically.
echo Keep this window OPEN while using the system.
echo.

REM Disable Streamlit's first-run email/usage prompt.
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

REM Start Streamlit in a separate process.
start "Packing Slip App Server" /B ".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false

REM Give the local server time to start, then force browser open.
timeout /t 5 /nobreak >nul
start "" "http://localhost:8501"

echo.
echo If the page does not open, manually type this into Chrome or Edge:
echo http://localhost:8501
echo.
echo Press any key here ONLY when you want to stop using the app.
pause >nul

REM Stop Streamlit processes launched from this environment.
taskkill /FI "WINDOWTITLE eq Packing Slip App Server*" /T /F >nul 2>nul
exit /b 0

:error
echo.
echo ==========================================
echo Something failed during setup.
echo Please take a photo or screenshot of the
echo error shown above and send it in this chat.
echo ==========================================
echo.
pause
exit /b 1
