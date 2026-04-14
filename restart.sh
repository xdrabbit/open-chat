#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_PYTHON="$ROOT_DIR/venv/bin/python"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/open-chat-backend.pid"
LOG_FILE="$RUNTIME_DIR/backend.log"
PORT=8282

if [ -f "$ROOT_DIR/.env" ]; then
    configured_port="$(sed -n "s/^[[:space:]]*PORT=//p" "$ROOT_DIR/.env" | tail -n1 | tr -d "\"'" | xargs)"
    if [ -n "${configured_port:-}" ]; then
        PORT="$configured_port"
    fi
fi

HEALTH_URL="http://127.0.0.1:${PORT}/health"

mkdir -p "$RUNTIME_DIR"

find_backend_pids() {
    {
        if [ -f "$PID_FILE" ]; then
            cat "$PID_FILE"
        fi
        ss -ltnp "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p'
        pgrep -f "$VENV_PYTHON main.py" || true
    } | awk 'NF' | sort -u
}

wait_for_exit() {
    local pid="$1"
    local remaining=20
    while [ "$remaining" -gt 0 ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        sleep 1
        remaining=$((remaining - 1))
    done
    return 1
}

stop_existing_backend() {
    mapfile -t pids < <(find_backend_pids)
    if [ "${#pids[@]}" -eq 0 ]; then
        echo "No running backend found on port $PORT."
        rm -f "$PID_FILE"
        return 0
    fi

    echo "Stopping existing backend: ${pids[*]}"
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done

    for pid in "${pids[@]}"; do
        if ! wait_for_exit "$pid"; then
            echo "Backend pid $pid did not exit cleanly; forcing shutdown."
            kill -9 "$pid" 2>/dev/null || true
        fi
    done

    rm -f "$PID_FILE"
}

start_backend() {
    if [ ! -x "$VENV_PYTHON" ]; then
        echo "Virtualenv python not found at $VENV_PYTHON"
        echo "Run ./start.sh first."
        exit 1
    fi

    echo "Starting backend..."
    cd "$BACKEND_DIR"
    nohup "$VENV_PYTHON" main.py >> "$LOG_FILE" 2>&1 < /dev/null &
    echo $! > "$PID_FILE"
    cd "$ROOT_DIR"
}

stop_existing_backend
start_backend

backend_pid="$(cat "$PID_FILE")"
sleep 2

if ! kill -0 "$backend_pid" 2>/dev/null; then
    echo "Backend process exited immediately."
    echo "Last log lines:"
    tail -n 40 "$LOG_FILE" || true
    exit 1
fi

if ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
    echo "Backend restarted successfully."
else
    echo "Backend restarted and is still warming up."
fi

echo "PID: $backend_pid"
echo "Health URL: $HEALTH_URL"
echo "Log: $LOG_FILE"
