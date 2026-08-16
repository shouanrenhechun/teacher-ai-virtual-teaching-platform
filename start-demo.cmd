@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] backend\.venv not found.
  echo Create it with: py -3.12 -m venv .venv
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo [ERROR] frontend\node_modules not found.
  echo Run: cd frontend ^&^& npm.cmd ci
  pause
  exit /b 1
)

echo ===============================================
echo   DEMO MODE / MOCK
echo   Real LLM will not be called.
echo ===============================================
echo.

start "AI Teaching Demo Backend - MOCK" cmd /k "cd /d ""%~dp0backend"" ^&^& set LLM_PROVIDER=mock ^&^& set RUN_REAL_LLM_VALIDATION=false ^&^& set LLM_MODEL=mock ^&^& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "AI Teaching Demo Frontend" cmd /k "cd /d ""%~dp0frontend"" ^&^& npm.cmd run dev -- --host 127.0.0.1 --port 5173"

echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo Close the two child terminals to stop the demo.
endlocal
