#!/usr/bin/env bash
set -eo pipefail
STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$STUDIO_ROOT"
python3 -c 'import json,urllib.request; s=json.load(urllib.request.urlopen("http://127.0.0.1:8765/e2e/status")); assert s["job"]["state"] not in ("running","stopping"), "Stop evaluation first"'
curl --fail -s -X POST http://127.0.0.1:8765/scenes/save -H 'Content-Type: application/json' -d '{"name":"原生服务升级前快照"}' > /dev/null
# Release the native client before its server goes away. Browser polling against
# a stale CARLA client can otherwise terminate Python inside the C++ extension.
bash scripts/restart_studio_bridge.sh --stop
if [[ -f .runtime/carla.pid ]]; then
  CARLA_NATIVE_PID="$(<.runtime/carla.pid)"
  [[ "$CARLA_NATIVE_PID" =~ ^[0-9]+$ ]] || exit 1
  if kill -0 "$CARLA_NATIVE_PID" 2>/dev/null; then
    tr '\0' ' ' < "/proc/$CARLA_NATIVE_PID/cmdline" | rg -q '/CarlaUE4/CarlaUE4.uproject' || exit 1
    kill -TERM "$CARLA_NATIVE_PID"
    for attempt in {1..100}; do
      kill -0 "$CARLA_NATIVE_PID" 2>/dev/null || break
      sleep .2
    done
    if kill -0 "$CARLA_NATIVE_PID" 2>/dev/null; then echo 'Old server has not exited' >&2; exit 1; fi
  fi
fi
setsid /home/moresweet/UnrealEngine_4.26/Engine/Binaries/Linux/UE4Editor \
  /home/moresweet/carla/Unreal/CarlaUE4/CarlaUE4.uproject /Game/Carla/Maps/Town04 \
  -game -windowed -ResX=1280 -ResY=720 -carla-server -carla-port=2000 \
  -quality-level=Low '-ExecCmds=r.GPUScene 0' >> .runtime/carla.log 2>&1 < /dev/null &
echo "$!" > .runtime/carla.pid
for attempt in {1..60}; do
  if PYTHONPATH=/home/moresweet/carla/.venv/lib/python3.14/site-packages python3 -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(2); print(c.get_world().get_map().name)' 2>/dev/null; then
    bash scripts/restart_studio_bridge.sh
    exit 0
  fi
  sleep .5
done
echo 'Server not ready; inspect .runtime/carla.log' >&2
exit 1
