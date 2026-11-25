#!/bin/zsh
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "============================================"
echo "             TATHYA-DF STARTUP"
echo "============================================"

command -v python3.12 >/dev/null 2>&1 || {
  echo "Python 3.12 is required. Install it from https://www.python.org/downloads/"
  read "?Press Return to close..."
  exit 1
}
command -v node >/dev/null 2>&1 || {
  echo "Node.js 22 LTS is required. Install it from https://nodejs.org/"
  read "?Press Return to close..."
  exit 1
}
command -v npm >/dev/null 2>&1 || {
  echo "npm was not found. Reinstall Node.js."
  read "?Press Return to close..."
  exit 1
}

if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
  echo "[1/4] Creating backend virtual environment..."
  python3.12 -m venv "$ROOT/backend/.venv"
fi

echo "[2/4] Installing/verifying backend dependencies..."
"$ROOT/backend/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/backend/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"

if ! "$ROOT/backend/.venv/bin/python" -c "import spacy; spacy.load('en_core_web_sm')" >/dev/null 2>&1; then
  echo "Installing spaCy English language model..."
  "$ROOT/backend/.venv/bin/python" -m spacy download en_core_web_sm
fi

if [[ ! -f "$ROOT/backend/.env" ]]; then
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "[3/4] Installing frontend dependencies..."
  (cd "$ROOT/frontend" && npm ci)
else
  echo "[3/4] Frontend dependencies already installed."
fi

echo "[4/4] Opening backend and frontend in Terminal..."
BACKEND_CMD="cd ${(q)ROOT}/backend && ${(q)ROOT}/backend/.venv/bin/python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000"
FRONTEND_CMD="cd ${(q)ROOT}/frontend && npm run dev -- --host 127.0.0.1"
osascript <<APPLESCRIPT
tell application "Terminal"
  activate
  do script "$BACKEND_CMD"
  delay 2
  do script "$FRONTEND_CMD"
end tell
APPLESCRIPT

sleep 3
open "http://localhost:5173"
echo "TATHYA-DF is starting. Keep both Terminal windows open."
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000/docs"
