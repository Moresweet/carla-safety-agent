#!/usr/bin/env bash
set -eo pipefail
STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$STUDIO_ROOT"
if [[ -f .runtime/bridge.pid ]]; then
  BRIDGE_PID="$(<.runtime/bridge.pid)"
  [[ "$BRIDGE_PID" =~ ^[0-9]+$ ]] || { echo 'Invalid bridge PID' >&2; exit 1; }
  if kill -0 "$BRIDGE_PID" 2>/dev/null; then
    [[ "$(readlink "/proc/$BRIDGE_PID/cwd")" == "$STUDIO_ROOT" ]] || { echo 'Bridge working directory mismatch' >&2; exit 1; }
    tr '\0' ' ' < "/proc/$BRIDGE_PID/cmdline" | rg -q 'tools/livery_bridge.py' || exit 1
    PYTHONPATH="$STUDIO_ROOT/src" python3 tools/check_bridge_restart.py
    kill -TERM "$BRIDGE_PID"
    for attempt in {1..30}; do
      kill -0 "$BRIDGE_PID" 2>/dev/null || break
      sleep .1
    done
    if kill -0 "$BRIDGE_PID" 2>/dev/null; then
      echo 'Old bridge has not exited; refusing a duplicate process' >&2
      exit 1
    fi
  fi
fi
if [[ "${1:-}" == '--stop' ]]; then exit 0; fi
mkdir -p .runtime
setsid env PYTHONPATH="${CARLA_PYTHONPATH:-/home/moresweet/carla/.venv/lib/python3.14/site-packages}" \
  python3 tools/livery_bridge.py >> .runtime/bridge.log 2>&1 < /dev/null &
echo "$!" > .runtime/bridge.pid
echo "Bridge started: $!"
for attempt in {1..30}; do
  curl --fail -s --max-time 1 http://127.0.0.1:8765/session/status && exit 0
  sleep .2
done
echo 'Bridge failed to become ready; inspect .runtime/bridge.log' >&2
exit 1
