#!/usr/bin/env bash
set -euo pipefail

E2E_ROOT="${E2E_ROOT:-/home/moresweet/Data/e2e}"
B2D="${BENCH2DRIVE_ROOT:-$E2E_ROOT/Bench2Drive}"
ZOO="${BENCH2DRIVE_ZOO:-$E2E_ROOT/Bench2DriveZoo}"
TCP_ZOO="${BENCH2DRIVE_TCP_ZOO:-$E2E_ROOT/Bench2DriveZoo-tcp-admlp}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CARLA_ROOT="${CARLA_ROOT:-/home/moresweet/carla}"
UNIAD_PYTHON="${UNIAD_PYTHON:-$E2E_ROOT/miniconda3/envs/uniad-cu128/bin/python}"
EXECUTION_MODE="${E2E_EXECUTION_MODE:-preset}"
if [[ "$EXECUTION_MODE" == scenario ]]; then
  ROUTES="${SCENARIO:?SCENARIO is required}"
  ROUTE_ID=generated
elif [[ "$EXECUTION_MODE" == preset ]]; then
  ROUTES="${ROUTES:?ROUTES is required}"
  ROUTE_ID="${ROUTE_ID:?ROUTE_ID is required}"
else
  echo 'Unsupported execution mode' >&2; exit 2
fi
ALGORITHM="${ALGORITHM:-uniad-tiny}"
RESULTS="${RESULTS:-$REPO_ROOT/runs/benchmark/preset.json}"
RUN_NAME="preset-${ROUTE_ID}-$(date +%Y%m%d-%H%M%S)"

mkdir -p "$(dirname "$RESULTS")" "$REPO_ROOT/runs/benchmark/sensors"
case "$ALGORITHM" in
  uniad-tiny)
    MODEL_ROOT="$ZOO"
    AGENT="$ZOO/team_code/uniad_b2d_agent.py"
    CONFIG="$ZOO/adzoo/uniad/configs/stage2_e2e/tiny_e2e_b2d.py+$ZOO/ckpts/uniad_tiny_b2d.pth+$RUN_NAME" ;;
  uniad-base)
    MODEL_ROOT="$ZOO"
    AGENT="$ZOO/team_code/uniad_b2d_agent.py"
    CONFIG="$ZOO/adzoo/uniad/configs/stage2_e2e/base_e2e_b2d.py+$ZOO/ckpts/uniad_base_b2d.pth+$RUN_NAME" ;;
  vad)
    MODEL_ROOT="$ZOO"
    AGENT="$REPO_ROOT/integration/bench2drive/vad_agent.py"
    CONFIG="$ZOO/adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py+$ZOO/ckpts/vad_b2d_base.pth+$RUN_NAME" ;;
  tcp)
    MODEL_ROOT="$TCP_ZOO"
    AGENT="$REPO_ROOT/integration/bench2drive/tcp_agent.py"
    CONFIG="$TCP_ZOO/ckpts/tcp_b2d.ckpt+$RUN_NAME" ;;
  admlp)
    MODEL_ROOT="$TCP_ZOO"
    AGENT="$REPO_ROOT/integration/bench2drive/admlp_agent.py"
    CONFIG="$TCP_ZOO/ckpts/admlp_b2d.ckpt+$RUN_NAME" ;;
  *) echo "Unsupported algorithm: $ALGORITHM" >&2; exit 2 ;;
esac

[[ -f "$AGENT" ]] || { echo "Missing adapter: $AGENT" >&2; exit 2; }
if [[ "$ALGORITHM" == uniad-* || "$ALGORITHM" == vad ]]; then
  CHECKPOINT="${CONFIG#*+}"
  CHECKPOINT="${CHECKPOINT%%+*}"
else
  CHECKPOINT="${CONFIG%%+*}"
fi
[[ -f "$CHECKPOINT" ]] || { echo "Missing checkpoint: $CHECKPOINT" >&2; exit 2; }

if [[ "${E2E_CHECK_ONLY:-0}" == 1 ]]; then
  printf 'algorithm=%s\nagent=%s\ncheckpoint=%s\nconfig=%s\n' \
    "$ALGORITHM" "$AGENT" "$CHECKPOINT" "$CONFIG"
  exit 0
fi

export PYTHONPATH="$B2D/leaderboard:$B2D/scenario_runner:$REPO_ROOT/src:$CARLA_ROOT/PythonAPI/carla:$E2E_ROOT:$MODEL_ROOT"
export CARLA_ROOT CARLA_SERVER="$CARLA_ROOT/CarlaUE4.sh"
export BENCH2DRIVE_EXISTING_SERVER=1 IS_BENCH2DRIVE=True PLANNER_TYPE=only_traj
export CSA_ALGORITHM_LABEL="$ALGORITHM"
export SCENARIO_RUNNER_ROOT="$B2D/scenario_runner"
export SAVE_PATH="$REPO_ROOT/runs/benchmark/sensors"

cd "$B2D"
if [[ "$EXECUTION_MODE" == scenario ]]; then
  [[ -f "$SCENARIO" ]] || { echo 'Missing scenario archive' >&2; exit 2; }
  exec "$UNIAD_PYTHON" -m carla_safety_agent.native_executor \
    --scenario "$SCENARIO" --agent "$AGENT" --agent-config "$CONFIG" \
    --output "$RESULTS" --port="${CARLA_PORT:-2000}"
fi
exec "$UNIAD_PYTHON" "$REPO_ROOT/integration/bench2drive/leaderboard_evaluator.py" \
  --routes="$ROUTES" --routes-subset="$ROUTE_ID" --repetitions=1 --track=SENSORS \
  --checkpoint="$RESULTS" --debug-checkpoint="${RESULTS%.json}.txt" \
  --agent="$AGENT" --agent-config="$CONFIG" \
  --debug=0 --record="" --port="${CARLA_PORT:-2000}" \
  --traffic-manager-port="${TM_PORT:-8000}" --gpu-rank=0
