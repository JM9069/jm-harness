#!/usr/bin/env bash
# jm 허브 켜기 · 끄기 · 상태 — 백그라운드로 띄우고 PID 파일로만 끈다
#   bash jmkit/start.sh            작업 폴더(~/workspace, 없으면 현재 폴더)를 포트 3156 으로
#   bash jmkit/start.sh stop | status
set -u
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
PORT="${JM_PORT:-3156}"
ROOT="${JM_ROOT:-$( [ -d "$HOME/workspace" ] && echo "$HOME/workspace" || pwd )}"
STATE="$HOME/.jm"; mkdir -p "$STATE"
PIDF="$STATE/hub-$PORT.pid"; OUT="$STATE/hub-$PORT.out"

alive() { [ -f "$PIDF" ] && [ -r "/proc/$(cat "$PIDF")/cmdline" ] && tr '\0' ' ' < "/proc/$(cat "$PIDF")/cmdline" | grep -q "hub.py"; }

case "${1:-start}" in
start)
    if alive; then echo "이미 실행 중 (PID $(cat "$PIDF")) — IDE Browser PORT $PORT"; exit 0; fi
    nohup python3 "$HERE/hub.py" --root "$ROOT" --port "$PORT" > "$OUT" 2>&1 < /dev/null &
    echo $! > "$PIDF"
    for _ in $(seq 1 40); do
        if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/health', timeout=1)" 2>/dev/null; then
            echo "jm 허브 실행 — 작업 폴더 $ROOT · IDE Browser PORT $PORT (끄기: bash $HERE/start.sh stop)"; exit 0
        fi
        if ! kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "실행 실패:"; cat "$OUT"; rm -f "$PIDF"; exit 1; fi
        sleep 0.25
    done
    echo "응답 없음 — $OUT 확인"; exit 1 ;;
stop)
    if alive; then kill "$(cat "$PIDF")" && echo "정지 (포트 $PORT)"; else echo "실행 중 아님 (포트 $PORT)"; fi
    rm -f "$PIDF" ;;
status)
    if alive; then echo "실행 중 — PID $(cat "$PIDF") · 포트 $PORT"; else echo "실행 중 아님 (포트 $PORT)"; fi ;;
*) echo "사용: bash start.sh [start|stop|status]"; exit 2 ;;
esac
