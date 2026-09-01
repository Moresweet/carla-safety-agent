#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${SURFACE_RUNTIME_DIR:-$ROOT_DIR/.runtime}"

stop_process() {
  local name="$1"
  local expected="$2"
  local pid_file="$RUNTIME_DIR/$name.pid"
  [[ -f "$pid_file" ]] || { echo "$name is not recorded as running"; return; }
  local pid
  pid="$(<"$pid_file")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || [[ ! -d "/proc/$pid" ]]; then
    echo "$name is already stopped"
    rm -f "$pid_file"
    return
  fi
  local command_line
  command_line="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null)"
  if [[ "$command_line" != *"$expected"* ]]; then
    echo "Refusing to stop PID $pid for $name: command no longer matches $expected" >&2
    return 1
  fi
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for ((i=0; i<15; i++)); do
    [[ -d "/proc/$pid" ]] || break
    sleep 1
  done
  if [[ -d "/proc/$pid" ]]; then
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
  echo "Stopped $name"
}

stop_process frontend "livery-designer"
stop_process bridge "livery_bridge.py"
stop_process carla "CarlaUE4.uproject"
