#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${SURFACE_RUNTIME_DIR:-$ROOT_DIR/.runtime}"
CARLA_ROOT="${CARLA_ROOT:-/home/moresweet/carla}"
UE4_ROOT="${UE4_ROOT:-/home/moresweet/UnrealEngine_4.26}"
CARLA_MAP="${CARLA_MAP:-Town04}"
if [[ "$CARLA_MAP" == /Game/* ]]; then
  CARLA_MAP_PATH="$CARLA_MAP"
else
  CARLA_MAP_PATH="/Game/Carla/Maps/$CARLA_MAP"
fi
CARLA_PORT="${CARLA_PORT:-2000}"
BRIDGE_PORT=8765
FRONTEND_PORT=3000
CARLA_PYTHONPATH="${CARLA_PYTHONPATH:-$CARLA_ROOT/.venv/lib/python3.14/site-packages}"
UE4_EDITOR="${UE4_EDITOR:-$UE4_ROOT/Engine/Binaries/Linux/UE4Editor}"
CARLA_PROJECT="${CARLA_PROJECT:-$CARLA_ROOT/Unreal/CarlaUE4/CarlaUE4.uproject}"
NODE_BIN="${NODE_BIN:-$(command -v node 2>/dev/null || true)}"
PNPM_BIN="${PNPM_BIN:-$(command -v pnpm 2>/dev/null || true)}"
CODEX_DEPS="/home/moresweet/.cache/codex-runtimes/codex-primary-runtime/dependencies"
[[ -n "$NODE_BIN" ]] || NODE_BIN="$CODEX_DEPS/node/bin/node"
[[ -n "$PNPM_BIN" ]] || PNPM_BIN="$CODEX_DEPS/bin/fallback/pnpm"

mkdir -p "$RUNTIME_DIR"

fail() { echo "ERROR: $*" >&2; exit 1; }
port_open() { (echo >"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1; }
wait_port() {
  local port="$1" name="$2" limit="$3"
  for ((i=0; i<limit; i++)); do
    port_open "$port" && return 0
    sleep 1
  done
  echo "$name did not open port $port within ${limit}s" >&2
  return 1
}
start_process() {
  local name="$1"; shift
  setsid "$@" >"$RUNTIME_DIR/$name.log" 2>&1 &
  local pid=$!
  echo "$pid" >"$RUNTIME_DIR/$name.pid"
  echo "Started $name (PID $pid, log $RUNTIME_DIR/$name.log)"
}

[[ -x "$UE4_EDITOR" ]] || fail "UE4Editor not found: $UE4_EDITOR"
[[ -f "$CARLA_PROJECT" ]] || fail "CARLA project not found: $CARLA_PROJECT"
[[ -d "$CARLA_PYTHONPATH" ]] || fail "CARLA Python path not found: $CARLA_PYTHONPATH"
command -v python3 >/dev/null || fail "python3 is not available"
[[ -x "$NODE_BIN" ]] || fail "node is not available; set NODE_BIN"
[[ -x "$PNPM_BIN" ]] || fail "pnpm is not available; set PNPM_BIN"

for port in "$CARLA_PORT" "$BRIDGE_PORT" "$FRONTEND_PORT"; do
  port_open "$port" && fail "Port $port is already occupied. Run scripts/stop_surface_studio.sh or stop the existing service."
done

cleanup_on_error() {
  local code=$?
  if (( code != 0 )); then
    "$ROOT_DIR/scripts/stop_surface_studio.sh" >/dev/null 2>&1 || true
    echo "Startup failed. Inspect logs under $RUNTIME_DIR." >&2
  fi
  exit "$code"
}
trap cleanup_on_error EXIT

start_process carla "$UE4_EDITOR" "$CARLA_PROJECT" "$CARLA_MAP_PATH" \
  -game -windowed -ResX=1280 -ResY=720 -carla-server \
  "-carla-port=$CARLA_PORT" -quality-level=Low
wait_port "$CARLA_PORT" CARLA 120

start_process bridge env PYTHONPATH="$CARLA_PYTHONPATH" \
  CARLA_PORT="$CARLA_PORT" \
  python3 "$ROOT_DIR/tools/livery_bridge.py"
wait_port "$BRIDGE_PORT" "texture bridge" 30

start_process frontend env PATH="$(dirname "$NODE_BIN"):$(dirname "$PNPM_BIN"):$PATH" \
  "$PNPM_BIN" --dir "$ROOT_DIR/tools/livery-designer" run dev \
  -- --host 127.0.0.1 --port "$FRONTEND_PORT"
wait_port "$FRONTEND_PORT" "Surface Studio" 60

trap - EXIT
echo
echo "Surface Studio is ready: http://localhost:$FRONTEND_PORT/"
echo "CARLA RPC: 127.0.0.1:$CARLA_PORT"
echo "Stop everything with: $ROOT_DIR/scripts/stop_surface_studio.sh"
