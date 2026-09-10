# Shared local paths. Source before launch; explicit environment values win.
# This file only exports paths: it never starts services or creates directories.
export CARLA_ROOT="${CARLA_ROOT:-/home/moresweet/carla}"
export UE4_ROOT="${UE4_ROOT:-/home/moresweet/UnrealEngine_4.26}"
export UE4_EDITOR="${UE4_EDITOR:-$UE4_ROOT/Engine/Binaries/Linux/UE4Editor}"
export UE4_EDITOR_CMD="${UE4_EDITOR_CMD:-$UE4_ROOT/Engine/Binaries/Linux/UE4Editor-Cmd}"
export CARLA_PROJECT="${CARLA_PROJECT:-$CARLA_ROOT/Unreal/CarlaUE4/CarlaUE4.uproject}"
export CARLA_PYTHONPATH="${CARLA_PYTHONPATH:-$CARLA_ROOT/.venv/lib/python3.14/site-packages}"
export E2E_ROOT="${E2E_ROOT:-/home/moresweet/Data/e2e}"
export UNIAD_PYTHON="${UNIAD_PYTHON:-$E2E_ROOT/miniconda3/envs/uniad-cu128/bin/python}"
export BLENDER_BIN="${BLENDER_BIN:-/snap/bin/blender}"
