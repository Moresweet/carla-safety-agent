#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/integration/docker/compose.yaml")
case "${1:-help}" in
  start)
    if [[ "${HEADLESS:-0}" != 1 ]]; then
      command -v xauth >/dev/null || { echo 'Install xauth on the display host'; exit 1; }
      # Export only the current display cookie, never mount the home directory.
      mkdir -p "$ROOT/.runtime"
      existing_auth="$(docker inspect carla-safety-studio-1 --format '{{range .Mounts}}{{if eq .Destination "/tmp/csa.xauth"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)"
      # Reuse the existing display mount so repeated starts do not discard UE caches.
      if [[ -z "${CSA_XAUTHORITY:-}" && -f "$existing_auth" && -O "$existing_auth" && ! -L "$existing_auth" ]]; then
        case "$existing_auth" in
          "$ROOT/.runtime/docker.xauth"|/tmp/csa-xauth.*) export CSA_XAUTHORITY="$existing_auth" ;;
        esac
      fi
      export CSA_XAUTHORITY="${CSA_XAUTHORITY:-$ROOT/.runtime/docker.xauth}"
      [[ ! -L "$CSA_XAUTHORITY" ]] || { echo 'Refusing a symlink for display authorization'; exit 1; }
      touch "$CSA_XAUTHORITY"
      chmod 600 "$CSA_XAUTHORITY"
      xauth nlist "${DISPLAY:-:0}" | sed 's/^..../ffff/' | xauth -f "$CSA_XAUTHORITY" nmerge -
      [[ -s "$CSA_XAUTHORITY" ]] || { echo 'No display cookie found; set XAUTHORITY or use HEADLESS=1'; exit 1; }
      chmod 600 "$CSA_XAUTHORITY"
    else
      export CSA_XAUTHORITY=/dev/null
    fi
    "${COMPOSE[@]}" up -d studio
    ;;
  stop) "${COMPOSE[@]}" stop ;;
  logs) "${COMPOSE[@]}" exec -T studio bash -c 'tail -n 60 /workspace/.runtime/docker-*.log' ;;
  check) "${COMPOSE[@]}" exec -T studio /opt/csa/entrypoint.sh check ;;
  ros) "${COMPOSE[@]}" exec -d studio /opt/csa/entrypoint.sh ros ;;
  rviz) "${COMPOSE[@]}" exec -d studio /opt/csa/entrypoint.sh rviz ;;
  *) echo 'Usage: bash scripts/docker_studio.sh {start|stop|logs|check|ros|rviz}' ;;
esac
