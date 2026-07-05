@echo off
cd /d "%~dp0"

echo [1/2] Starting Backend (uvicorn)...
start "Backend" cmd /k "cd /d backend && uvicorn app.main:app --port 8000"
timeout /t 3 /nobreak >nul

echo [2/2] Starting Frontend (Vite)...
start "Frontend" cmd /k "cd /d frontend && npm run dev"

echo.
echo Both services are starting up!
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo Close the windows to stop the services.
pause
