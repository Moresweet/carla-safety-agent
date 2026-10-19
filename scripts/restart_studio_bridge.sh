#!/usr/bin/env bash
set -eo pipefail
STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$STUDIO_ROOT"
source "$STUDIO_ROOT/scripts/studio_paths.sh"
if [[ "$#" -gt 1 || ( "${1:-}" != '' && "${1:-}" != '--stop' && "${1:-}" != '--after-crash-stop' && "${1:-}" != '--resume-recovery' && "${1:-}" != '--upgrade-legacy-assets' ) ]]; then
  echo 'Usage: restart_studio_bridge.sh [--stop|--after-crash-stop|--resume-recovery|--upgrade-legacy-assets]' >&2; exit 1
fi
# Keep admission closed through status inspection and old bridge exit. The
# replacement must not inherit this exclusive lock.
mkdir -p .runtime/blender-assets
exec 9>>.runtime/blender-assets/bridge-restart.lock
flock -n -x 9 || { echo 'Asset operation or bridge restart active; refusing restart' >&2; exit 1; }
# Older import workers inherited this lock before the admission lock existed.
# Hold it through the old bridge exit too; legacy import requests cannot start.
exec 8>>.runtime/blender-assets/import.lock
flock -n -x 8 || { echo 'Native asset import active; refusing restart' >&2; exit 1; }
if [[ -f .runtime/bridge.pid ]]; then
  BRIDGE_PID="$(<.runtime/bridge.pid)"
  [[ "$BRIDGE_PID" =~ ^[0-9]+$ ]] || { echo 'Invalid bridge PID' >&2; exit 1; }
  if kill -0 "$BRIDGE_PID" 2>/dev/null; then
    [[ "$(readlink "/proc/$BRIDGE_PID/cwd")" == "$STUDIO_ROOT" ]] || { echo 'Bridge working directory mismatch' >&2; exit 1; }
    python3 - "$BRIDGE_PID" <<'PY'
import sys
from pathlib import Path
pid = int(sys.argv[1])
argv = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
if argv != [b'python3', b'tools/livery_bridge.py', b'']:
    raise SystemExit('Bridge command identity mismatch; refusing to signal process')
PY
    if [[ "${1:-}" == '--after-crash-stop' ]]; then
      PYTHONPATH="$STUDIO_ROOT/src" python3 tools/check_bridge_restart.py --after-crash
    elif [[ "${1:-}" == '--resume-recovery' ]]; then
      PYTHONPATH="$STUDIO_ROOT/src" python3 tools/check_bridge_restart.py --resume-recovery
    elif [[ "${1:-}" == '--upgrade-legacy-assets' ]]; then
      PYTHONPATH="$STUDIO_ROOT/src" python3 tools/check_bridge_restart.py --legacy-assets
    else
      PYTHONPATH="$STUDIO_ROOT/src" python3 tools/check_bridge_restart.py
    fi
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
exec 9>&-
exec 8>&-
if [[ "${1:-}" == '--stop' || "${1:-}" == '--after-crash-stop' ]]; then exit 0; fi
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
