#!/usr/bin/env bash
set -euo pipefail

E2E_ROOT="${E2E_ROOT:-/home/moresweet/Data/e2e}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZOO="$E2E_ROOT/Bench2DriveZoo"
CARLA_ROOT="${CARLA_ROOT:-/home/moresweet/carla}"
SCENARIO="${SCENARIO:-}"
RESULTS="${RESULTS:-$PWD/runs/uniad/native-evaluation.json}"
PORT="${CARLA_PORT:-2000}"
UNIAD_PYTHON="${UNIAD_PYTHON:-$E2E_ROOT/miniconda3/envs/uniad-cu128/bin/python}"

[[ -x "$UNIAD_PYTHON" ]] || { echo "Missing UniAD Python: $UNIAD_PYTHON" >&2; exit 2; }

if [[ "${1:-}" == "--doctor" ]]; then
  exec "$UNIAD_PYTHON" "$REPO_ROOT/integration/uniad/doctor.py" --root "$E2E_ROOT" --carla-port "$PORT"
fi

for required in "$ZOO" "$SCENARIO" "$ZOO/ckpts/uniad_tiny_b2d.pth"; do
  [[ -e "$required" ]] || { echo "Missing required path: $required" >&2; exit 2; }
done

mkdir -p "$(dirname "$RESULTS")"

export CARLA_ROOT
export CARLA_SERVER="${CARLA_SERVER:-$CARLA_ROOT/CarlaUE4.sh}"
export PYTHONPATH="$REPO_ROOT/src:$CARLA_ROOT/PythonAPI/carla:$E2E_ROOT:$ZOO"
export IS_BENCH2DRIVE=True
export PLANNER_TYPE=traj
export SAVE_PATH="${SAVE_PATH:-$PWD/runs/uniad/sensors}"

RUN_NAME="${RUN_NAME:-$(basename "$SCENARIO" .json)-$(date +%Y%m%d-%H%M%S)}"
CONFIG="$ZOO/adzoo/uniad/configs/stage2_e2e/tiny_e2e_b2d.py+$ZOO/ckpts/uniad_tiny_b2d.pth+$RUN_NAME"
cd "$E2E_ROOT"
exec "$UNIAD_PYTHON" -m carla_safety_agent.native_executor \
  --scenario "$SCENARIO" --agent "$ZOO/team_code/uniad_b2d_agent.py" \
  --agent-config "$CONFIG" --output "$RESULTS" --port "$PORT"
