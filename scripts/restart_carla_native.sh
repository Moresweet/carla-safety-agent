#!/usr/bin/env bash
set -eo pipefail
STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$STUDIO_ROOT"
NATIVE_MAP="${CSA_NATIVE_MAP:-Town04}"
[[ "$NATIVE_MAP" =~ ^Town[0-9]+(HD)?(_Opt)?$ ]] || { echo 'Invalid native town name' >&2; exit 1; }
if [[ "${1:-}" != '' && "${1:-}" != '--after-crash' ]]; then
  echo 'Usage: restart_carla_native.sh [--after-crash]' >&2; exit 1
fi
if [[ "${1:-}" == '--after-crash' ]]; then
  PYTHONPATH=src python3 -c 'from carla_safety_agent.session import SessionJournal; assert SessionJournal("data").owned_pid() is None, "Stop live evaluation worker first"'
  if pgrep -x UE4Editor > /dev/null; then
    echo 'A native editor is still alive; refusing crash-recovery mode' >&2; exit 1
  fi
  echo 'Native process absent: current in-memory scene cannot be saved; retaining existing scene versions and datasets.'
else
  python3 -c 'import json,urllib.request; s=json.load(urllib.request.urlopen("http://127.0.0.1:8765/e2e/status",timeout=10)); assert s["job"]["state"] not in ("running","stopping"), "Stop evaluation first"'
  curl --fail -s -X POST http://127.0.0.1:8765/scenes/save -H 'Content-Type: application/json' -d '{"name":"原生服务升级前快照"}' > /dev/null
fi
# Release the native client before its server goes away. Browser polling against
# a stale CARLA client can otherwise terminate Python inside the C++ extension.
if [[ "${1:-}" == '--after-crash' ]]; then
  bash scripts/restart_studio_bridge.sh --after-crash-stop
else
  bash scripts/restart_studio_bridge.sh --stop
fi
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
NATIVE_LAUNCH=()
if [[ "${CSA_NATIVE_DEBUG:-0}" == '1' ]]; then
  NATIVE_LAUNCH=(gdb -q -batch -ex 'set pagination off' -ex 'set debuginfod enabled off'
    -ex 'disable pretty-printer' -ex 'set print static-members off'
    -ex 'set print elements 8' -ex 'set print max-depth 2'
    -ex 'handle SIGPIPE nostop noprint pass' -ex 'handle SIGTRAP nostop noprint nopass'
    -ex run -ex 'frame 1' -ex 'p Proxy'
    -ex 'info symbol *((void**)Proxy)'
    -ex 'p ((FStaticMeshSceneProxy*)Proxy)->DistanceFieldData'
    -ex 'p PrimitiveSceneProxy'
    -ex 'info symbol *((void**)PrimitiveSceneProxy)' -ex 'p *PrimitiveSceneProxy'
    -ex 'p ((FSkeletalMeshSceneProxy*)PrimitiveSceneProxy)->MeshObject'
    -ex 'info symbol *((void**)((FSkeletalMeshSceneProxy*)PrimitiveSceneProxy)->MeshObject)'
    -ex 'x/4gx ((FSkeletalMeshSceneProxy*)PrimitiveSceneProxy)->MeshObject'
    -ex 'p ((USkinnedMeshComponent*)PrimitiveSceneProxy->ComponentForDebuggingOnly)->MeshObject'
    -ex 'frame 2' -ex 'p PrimitiveSceneProxy'
    -ex 'info symbol *((void**)PrimitiveSceneProxy)'
    -ex 'p ((FStaticMeshSceneProxy*)PrimitiveSceneProxy)->DistanceFieldData'
    -ex 'thread apply all bt 20' --args)
fi
setsid "${NATIVE_LAUNCH[@]}" /home/moresweet/UnrealEngine_4.26/Engine/Binaries/Linux/UE4Editor \
  /home/moresweet/carla/Unreal/CarlaUE4/CarlaUE4.uproject "/Game/Carla/Maps/$NATIVE_MAP" \
  -game -windowed -ResX=1280 -ResY=720 -carla-server -carla-port=2000 \
  -quality-level=Low '-ExecCmds=r.GPUScene 0' >> .runtime/carla.log 2>&1 < /dev/null &
NATIVE_LAUNCH_PID="$!"
if [[ "${CSA_NATIVE_DEBUG:-0}" != '1' ]]; then echo "$NATIVE_LAUNCH_PID" > .runtime/carla.pid; fi
for attempt in {1..60}; do
  if ! kill -0 "$NATIVE_LAUNCH_PID" 2>/dev/null; then
    echo 'Native launcher exited before readiness; inspect .runtime/carla.log' >&2; exit 1
  fi
  if [[ "${CSA_NATIVE_DEBUG:-0}" == '1' ]]; then
    # The managed PID must be the inferior, never the debugger parent.
    NATIVE_INFERIOR_PID="$(pgrep -P "$NATIVE_LAUNCH_PID" -x UE4Editor || true)"
    if [[ "$NATIVE_INFERIOR_PID" =~ ^[0-9]+$ ]]; then echo "$NATIVE_INFERIOR_PID" > .runtime/carla.pid; fi
  fi
  if PYTHONPATH=/home/moresweet/carla/.venv/lib/python3.14/site-packages python3 -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(2); print(c.get_world().get_map().name)' 2>/dev/null; then
    bash scripts/restart_studio_bridge.sh
    exit 0
  fi
  sleep .5
done
echo 'Server not ready; inspect .runtime/carla.log' >&2
exit 1
