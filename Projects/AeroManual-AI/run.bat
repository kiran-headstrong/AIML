@echo off
cd /d "%~dp0"

set NO_PROXY=localhost,127.0.0.1
set no_proxy=localhost,127.0.0.1

REM Auto-detect uvicorn and streamlit — prefer .venv if present, else use PATH
set VENV_DIR=%~dp0..\..\..venv\Scripts
if exist "%VENV_DIR%\uvicorn.exe" (
    set UVICORN=%VENV_DIR%\uvicorn.exe
    set STREAMLIT=%VENV_DIR%\streamlit.exe
) else (
    set UVICORN=uvicorn
    set STREAMLIT=streamlit
)

echo Starting AeroManual-AI...
echo.

REM Start FastAPI backend in background
start "AeroManual-API" cmd /k "cd /d "%~dp0" && set NO_PROXY=localhost,127.0.0.1 && "%UVICORN%" app.api:app --host 127.0.0.1 --port 8000"

REM Wait a moment for API to start
timeout /t 3 /nobreak >nul

REM Start Streamlit UI
start "AeroManual-UI" cmd /k "cd /d "%~dp0" && set NO_PROXY=localhost,127.0.0.1 && "%STREAMLIT%" run ui.py --server.port 8501"

echo.
echo API running at: http://localhost:8000
echo UI  running at: http://localhost:8501
echo.
echo Close the opened terminal windows to stop the services.
pause
