#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONPATH="$CARLA_PYTHONPATH:/workspace/src${PYTHONPATH:+:$PYTHONPATH}"
case "${1:-studio}" in
  check)
    python3 /workspace/integration/carla/verify_external_environment.py --carla-root "$CARLA_ROOT"
    python3 -c 'import carla, PIL; print("CARLA Python and Pillow ready")'
    env -u PYTHONPATH "$UNIAD_PYTHON" -c 'import torch, carla, mmcv; print("UniAD:", torch.__version__, torch.version.cuda, "GPU:", torch.cuda.is_available())'
    set +u
    source /opt/ros/lyrical/setup.bash
    python3 -c 'import rclpy, sensor_msgs, tf2_ros; print("ROS imports ready")'
    node --version
    ;;
  ros)
    set +u
    source /opt/ros/lyrical/setup.bash
    export PYTHONPATH="/workspace/ros2/carla_safety_visualization:$PYTHONPATH"
    exec python3 -c 'from carla_safety_visualization.bridge import main; main()'
    ;;
  rviz)
    set +u
    source /opt/ros/lyrical/setup.bash
    exec rviz2 -d /workspace/ros2/carla_safety_visualization/rviz/carla_safety.rviz
    ;;
  studio)
    [[ -f /workspace/tools/livery_bridge.py ]] || { echo 'Mount the project at /workspace'; exit 2; }
    # Dependency volume overlays host node_modules, keeping host installation intact.
    if [[ ! -e /workspace/tools/livery-designer/node_modules/.csa-seeded ]]; then
      cp -a /opt/csa/frontend/node_modules/. /workspace/tools/livery-designer/node_modules/
      touch /workspace/tools/livery-designer/node_modules/.csa-seeded
    fi
    mkdir -p /workspace/.runtime
    children=()
    cleanup() { trap - EXIT TERM INT; for pid in "${children[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done; wait || true; }
    trap cleanup EXIT TERM INT
    for port in "${CARLA_PORT:-2000}" 3000 8765; do
      if (echo >/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
        echo "Port $port already occupied; stop the conflicting studio first"; exit 2
      fi
    done
    map="${CARLA_MAP:-Town04}"
    asset="/Game/Carla/Maps/$map"
    [[ ! -f "$CARLA_ROOT/Unreal/CarlaUE4/Content/Carla/Maps/$map/$map.umap" ]] || asset="$asset/$map"
    args=(-game -windowed -ResX=1280 -ResY=720 -carla-server "-carla-port=${CARLA_PORT:-2000}" -quality-level=Low '-ExecCmds=r.GPUScene 0')
    [[ "${HEADLESS:-0}" != 1 ]] || args+=(-RenderOffScreen)
    setsid "$UE4_ROOT/Engine/Binaries/Linux/UE4Editor" "$CARLA_ROOT/Unreal/CarlaUE4/CarlaUE4.uproject" "$asset" "${args[@]}" > /workspace/.runtime/docker-carla.log 2>&1 &
    children+=("$!")
    ready=0
    for ((i=0;i<${CARLA_START_TIMEOUT:-900};i++)); do
      if (echo >/dev/tcp/127.0.0.1/"${CARLA_PORT:-2000}") 2>/dev/null; then ready=1; break; fi
      kill -0 "${children[0]}" || { tail -60 /workspace/.runtime/docker-carla.log; exit 1; }
      (( i % 30 != 0 )) || echo "Waiting for CARLA RPC (${i}s; cold shader compilation may take several minutes)"
      sleep 1
    done
    [[ "$ready" == 1 ]] || { echo 'CARLA startup timed out'; exit 1; }
    setsid python3 /workspace/tools/livery_bridge.py > /workspace/.runtime/docker-bridge.log 2>&1 &
    children+=("$!")
    cd /workspace/tools/livery-designer
    setsid node node_modules/vinext/dist/cli.js dev --host 127.0.0.1 --port 3000 > /workspace/.runtime/docker-frontend.log 2>&1 &
    children+=("$!")
    wait -n "${children[@]}"
    ;;
  *) exec "$@" ;;
esac
