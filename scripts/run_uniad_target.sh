#!/usr/bin/env bash
set -euo pipefail

E2E_ROOT="${E2E_ROOT:-/home/moresweet/Data/e2e}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
B2D="$E2E_ROOT/Bench2Drive"
ZOO="$E2E_ROOT/Bench2DriveZoo"
CARLA_ROOT="${CARLA_ROOT:-/home/moresweet/carla}"
ROUTES="${ROUTES:-$B2D/leaderboard/data/routes_devtest.xml}"
RESULTS="${RESULTS:-$PWD/runs/uniad/bench2drive.json}"
PORT="${CARLA_PORT:-2000}"
TM_PORT="${TM_PORT:-8000}"
GPU_RANK="${GPU_RANK:-0}"
UNIAD_PYTHON="${UNIAD_PYTHON:-$E2E_ROOT/miniconda3/envs/uniad-cu128/bin/python}"

[[ -x "$UNIAD_PYTHON" ]] || { echo "Missing UniAD Python: $UNIAD_PYTHON" >&2; exit 2; }

if [[ "${1:-}" == "--doctor" ]]; then
  exec "$UNIAD_PYTHON" "$REPO_ROOT/integration/uniad/doctor.py" --root "$E2E_ROOT" --carla-port "$PORT"
fi

for required in "$B2D" "$ZOO" "$ROUTES" "$ZOO/ckpts/uniad_tiny_b2d.pth"; do
  [[ -e "$required" ]] || { echo "Missing required path: $required" >&2; exit 2; }
done

mkdir -p "$(dirname "$RESULTS")"
ln -sfn "$ZOO" "$B2D/Bench2DriveZoo"
mkdir -p "$B2D/leaderboard/team_code"
ln -sfn "$ZOO/team_code/uniad_b2d_agent.py" "$B2D/leaderboard/team_code/uniad_b2d_agent.py"
ln -sfn "$ZOO/team_code/pid_controller.py" "$B2D/leaderboard/team_code/pid_controller.py"
ln -sfn "$ZOO/team_code/planner.py" "$B2D/leaderboard/team_code/planner.py"

export CARLA_ROOT
export CARLA_SERVER="${CARLA_SERVER:-$CARLA_ROOT/CarlaUE4.sh}"
export PYTHONPATH="$REPO_ROOT/src:$CARLA_ROOT/PythonAPI/carla:$B2D:$B2D/leaderboard:$B2D/leaderboard/team_code:$B2D/scenario_runner:$ZOO"
export SCENARIO_RUNNER_ROOT="$B2D/scenario_runner"
export LEADERBOARD_ROOT="$B2D/leaderboard"
export CHALLENGE_TRACK_CODENAME=SENSORS
export IS_BENCH2DRIVE=True
export BENCH2DRIVE_EXISTING_SERVER="${BENCH2DRIVE_EXISTING_SERVER:-1}"
export PLANNER_TYPE=traj
export SAVE_PATH="${SAVE_PATH:-$PWD/runs/uniad/sensors}"

CONFIG="$ZOO/adzoo/uniad/configs/stage2_e2e/tiny_e2e_b2d.py+$ZOO/ckpts/uniad_tiny_b2d.pth"
cd "$B2D"
exec "$UNIAD_PYTHON" leaderboard/leaderboard/leaderboard_evaluator.py \
  --routes="$ROUTES" --repetitions=1 --track=SENSORS \
  --checkpoint="$RESULTS" --agent=leaderboard/team_code/uniad_b2d_agent.py \
  --agent-config="$CONFIG" --debug=0 --resume=True \
  --port="$PORT" --traffic-manager-port="$TM_PORT" --gpu-rank="$GPU_RANK"
