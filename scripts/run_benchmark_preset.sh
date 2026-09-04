#!/usr/bin/env bash
set -euo pipefail

E2E_ROOT="${E2E_ROOT:-/home/moresweet/Data/e2e}"
B2D="${BENCH2DRIVE_ROOT:-$E2E_ROOT/Bench2Drive}"
ZOO="${BENCH2DRIVE_ZOO:-$E2E_ROOT/Bench2DriveZoo}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CARLA_ROOT="${CARLA_ROOT:-/home/moresweet/carla}"
UNIAD_PYTHON="${UNIAD_PYTHON:-$E2E_ROOT/miniconda3/envs/uniad-cu128/bin/python}"
ROUTES="${ROUTES:?ROUTES is required}"
ROUTE_ID="${ROUTE_ID:?ROUTE_ID is required}"
RESULTS="${RESULTS:-$REPO_ROOT/runs/benchmark/preset.json}"
RUN_NAME="preset-${ROUTE_ID}-$(date +%Y%m%d-%H%M%S)"

mkdir -p "$(dirname "$RESULTS")" "$REPO_ROOT/runs/benchmark/sensors"
export PYTHONPATH="$B2D/leaderboard:$B2D/scenario_runner:$REPO_ROOT/src:$CARLA_ROOT/PythonAPI/carla:$E2E_ROOT:$ZOO"
export CARLA_ROOT CARLA_SERVER="$CARLA_ROOT/CarlaUE4.sh"
export BENCH2DRIVE_EXISTING_SERVER=1 IS_BENCH2DRIVE=True PLANNER_TYPE=traj
export SCENARIO_RUNNER_ROOT="$B2D/scenario_runner"
export SAVE_PATH="$REPO_ROOT/runs/benchmark/sensors"
CONFIG="$ZOO/adzoo/uniad/configs/stage2_e2e/tiny_e2e_b2d.py+$ZOO/ckpts/uniad_tiny_b2d.pth+$RUN_NAME"

cd "$B2D"
exec "$UNIAD_PYTHON" leaderboard/leaderboard/leaderboard_evaluator.py \
  --routes="$ROUTES" --routes-subset="$ROUTE_ID" --repetitions=1 --track=SENSORS \
  --checkpoint="$RESULTS" --debug-checkpoint="${RESULTS%.json}.txt" \
  --agent="$ZOO/team_code/uniad_b2d_agent.py" --agent-config="$CONFIG" \
  --debug=0 --record="" --port="${CARLA_PORT:-2000}" \
  --traffic-manager-port="${TM_PORT:-8000}" --gpu-rank=0
