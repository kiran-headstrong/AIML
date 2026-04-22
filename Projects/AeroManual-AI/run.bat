@echo off
cd /d "%~dp0"

set NO_PROXY=localhost,127.0.0.1
set no_proxy=localhost,127.0.0.1

echo Starting AeroManual-AI...
echo.

REM Start FastAPI backend in background
start "AeroManual-API" cmd /k "uvicorn app.api:app --host 0.0.0.0 --port 8000"

REM Wait a moment for API to start
timeout /t 3 /nobreak >nul

REM Start Streamlit UI
start "AeroManual-UI" cmd /k "streamlit run ui.py --server.port 8501"

echo.
echo API running at: http://localhost:8000
echo UI  running at: http://localhost:8501
echo.
echo Close the opened terminal windows to stop the services.
pause
