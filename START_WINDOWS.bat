@echo off
setlocal
cd /d "%~dp0"
title TATHYA-DF Launcher

echo ============================================
echo             TATHYA-DF STARTUP
echo ============================================
where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python Launcher not found. Install Python 3.12 from https://www.python.org/downloads/
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js not found. Install Node.js 22 LTS from https://nodejs.org/
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: npm not found. Reinstall Node.js with npm.
  pause
  exit /b 1
)

py -3.12 --version >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python 3.12 is required. Install Python 3.12 and enable the Python Launcher.
  pause
  exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [1/4] Creating backend virtual environment...
  py -3.12 -m venv "backend\.venv"
  if errorlevel 1 goto :fail
)
echo [2/4] Installing/verifying backend dependencies...
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 goto :fail

"backend\.venv\Scripts\python.exe" -c "import spacy; spacy.load('en_core_web_sm')" >nul 2>nul
if errorlevel 1 (
  echo Installing spaCy English language model...
  "backend\.venv\Scripts\python.exe" -m spacy download en_core_web_sm
  if errorlevel 1 goto :fail
)

if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul

if not exist "frontend\node_modules" (
  echo [3/4] Installing frontend dependencies...
  pushd frontend
  call npm ci
  if errorlevel 1 (popd & goto :fail)
  popd
) else (
  echo [3/4] Frontend dependencies already installed.
)

echo [4/4] Opening backend and frontend...
start "TATHYA-DF Backend" /D "%~dp0backend" cmd /k ""%~dp0backend\.venv\Scripts\python.exe" -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000"
timeout /t 3 /nobreak >nul
start "TATHYA-DF Frontend" /D "%~dp0frontend" cmd /k "npm run dev -- --host 127.0.0.1"
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"
echo.
echo TATHYA-DF is starting. Keep both terminal windows open.
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000/docs
echo.
exit /b 0

:fail
echo.
echo Startup failed. Read the error above, check the README prerequisites, then retry.
pause
exit /b 1
