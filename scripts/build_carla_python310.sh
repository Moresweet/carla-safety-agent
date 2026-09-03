#!/usr/bin/env bash
set -euo pipefail

E2E_ROOT="${E2E_ROOT:-/home/moresweet/Data/e2e}"
CARLA_ROOT="${CARLA_ROOT:-/home/moresweet/carla}"
UE4_ROOT="${UE4_ROOT:-/home/moresweet/UnrealEngine_4.26}"
ENV_PREFIX="${UNIAD_ENV_PREFIX:-$E2E_ROOT/miniconda3/envs/uniad-cu128}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ENV_PREFIX/bin/python"
BOOST_SOURCE="$CARLA_ROOT/Build/boost-1.90.0-c10-source"

[[ -x "$PYTHON" ]] || { echo "Missing environment: $ENV_PREFIX" >&2; exit 2; }
git -C "$CARLA_ROOT" apply --check "$REPO_ROOT/integration/uniad/carla-python310-conda-flags.patch" 2>/dev/null && \
  git -C "$CARLA_ROOT" apply "$REPO_ROOT/integration/uniad/carla-python310-conda-flags.patch" || true

env -u PYTHONPATH PATH="$ENV_PREFIX/bin:/usr/bin:/bin" TRAVIS=false UE4_ROOT="$UE4_ROOT" \
  bash "$CARLA_ROOT/Util/BuildTools/Setup.sh" --python-version=3.10 || true

[[ -x "$BOOST_SOURCE/b2" ]] || { echo "Boost source was not prepared" >&2; exit 2; }
if ! grep -q 'using gcc.*\/usr\/bin\/g++' "$BOOST_SOURCE/project-config.jam"; then
  echo 'using gcc : : /usr/bin/g++ ;' >> "$BOOST_SOURCE/project-config.jam"
fi
(cd "$BOOST_SOURCE" && ./b2 toolset=gcc python=3.10 link=static \
  cxxflags='-fPIC -std=c++14 -DBOOST_ERROR_CODE_HEADER_ONLY' -j "${BUILD_JOBS:-8}" \
  --with-python stage release)
cp "$BOOST_SOURCE/stage/lib/libboost_python310.a" \
  "$CARLA_ROOT/PythonAPI/carla/dependencies/lib/libboost_python310.a"

touch "$CARLA_ROOT/PythonAPI/carla/source/libcarla/libcarla.cpp"
env -u PYTHONPATH PATH="$ENV_PREFIX/bin:/usr/bin:/bin" \
  CPLUS_INCLUDE_PATH=/usr/include/c++/12:/usr/include/x86_64-linux-gnu/c++/12:/usr/include/c++/12/backward \
  UE4_ROOT="$UE4_ROOT" bash "$CARLA_ROOT/Util/BuildTools/BuildPythonAPI.sh" \
  --python-version=3.10 --build-wheel
"$PYTHON" -m pip install --force-reinstall \
  "$CARLA_ROOT/PythonAPI/carla/dist/carla-0.9.16-cp310-cp310-linux_x86_64.whl"
"$PYTHON" -c 'import carla; print("CARLA Python API import: OK")'
