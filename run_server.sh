#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${1:-${PORT:-12338}}"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
LOG_FILE="$LOG_DIR/server_${TIMESTAMP}.log"
LATEST_LOG="$LOG_DIR/latest.log"

if [ -f ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "No python interpreter found."
  exit 1
fi

echo "============================================"
echo "  academic-skill-backend"
echo "============================================"
echo "Python: $PYTHON_BIN"
echo "Host:   $HOST"
echo "Port:   $PORT"
echo "Docs:   http://127.0.0.1:$PORT/docs"
echo "Health: http://127.0.0.1:$PORT/healthz"
echo "Log:    $LOG_FILE"
echo "============================================"
echo ""

if [ ! -f ".env" ]; then
  echo "Missing .env file."
  echo "Create it first: cp .env.example .env"
  exit 1
fi

if ! "$PYTHON_BIN" -c "import fastapi, uvicorn, httpx, boto3, dotenv" >/dev/null 2>&1; then
  echo "Missing runtime dependencies."
  echo "Install them with:"
  echo "  $PYTHON_BIN -m pip install -e ."
  exit 1
fi

if command -v lsof >/dev/null 2>&1; then
  EXISTING_LISTENER="$(lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P 2>/dev/null || true)"
  if [ -n "$EXISTING_LISTENER" ]; then
    echo "Port $PORT is already in use."
    echo "$EXISTING_LISTENER"
    echo "Use another port, for example: ./run_server.sh 8020"
    exit 1
  fi
fi

ln -sf "$LOG_FILE" "$LATEST_LOG"
export PYTHONUNBUFFERED=1

echo "Starting server..."
echo "Tail logs with: tail -f $LATEST_LOG"
echo ""

exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1
