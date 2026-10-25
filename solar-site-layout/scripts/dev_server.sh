#!/usr/bin/env bash
# Start/stop a local solar-site-layout server tracked by a PID file (no process-name matching).
#   scripts/dev_server.sh start DATA_DIR PORT
#   scripts/dev_server.sh stop
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
pidfile="${SOLAR_SERVER_PIDFILE:-${TMPDIR:-/tmp}/solar-site-layout-server.pid}"
case "${1:-}" in
  start)
    data_dir="$2"; port="$3"
    setsid "$here/.venv/bin/solar-layout" --data-dir "$data_dir" serve --host 127.0.0.1 --port "$port" \
      > "${data_dir%/}.server.log" 2>&1 < /dev/null &
    echo $! > "$pidfile"
    for _ in $(seq 1 50); do
      if curl -fsS "http://127.0.0.1:$port/api/health" > /dev/null 2>&1; then echo "started pid $(cat "$pidfile") on $port"; exit 0; fi
      sleep 0.2
    done
    echo "server did not become healthy" >&2; exit 1 ;;
  stop)
    if [[ -f "$pidfile" ]]; then
      pid="$(cat "$pidfile")"
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      rm -f "$pidfile"; echo "stopped $pid"
    fi ;;
  *) echo "usage: $0 start DATA_DIR PORT | stop" >&2; exit 2 ;;
esac
