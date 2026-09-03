#!/usr/bin/env bash
set -euo pipefail

E2E_ROOT="${E2E_ROOT:-/home/moresweet/Data/e2e}"
CONDA_ROOT="${CONDA_ROOT:-$E2E_ROOT/miniconda3}"
ENV_PREFIX="${UNIAD_ENV_PREFIX:-$CONDA_ROOT/envs/uniad-cu128}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER="${MINICONDA_INSTALLER:-/tmp/Miniconda3-latest-Linux-x86_64.sh}"
INSTALLER_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
INSTALLER_SHA256="e8b25b92b262499141c5bd57a98d3c008024185fa951494b9cd9b6d94e72338b"

mkdir -p "$E2E_ROOT"
if [[ ! -x "$CONDA_ROOT/bin/conda" ]]; then
  [[ -f "$INSTALLER" ]] || curl -fL "$INSTALLER_URL" -o "$INSTALLER"
  echo "$INSTALLER_SHA256  $INSTALLER" | sha256sum --check
  bash "$INSTALLER" -b -p "$CONDA_ROOT"
fi

"$CONDA_ROOT/bin/conda" env create -p "$ENV_PREFIX" \
  --file "$REPO_ROOT/integration/uniad/environment-cu128.yml" || \
"$CONDA_ROOT/bin/conda" env update -p "$ENV_PREFIX" \
  --file "$REPO_ROOT/integration/uniad/environment-cu128.yml" --prune

PYTHON="$ENV_PREFIX/bin/python"
"$PYTHON" -m pip install --index-url https://download.pytorch.org/whl/cu128 \
  torch==2.7.1 torchvision==0.22.1
"$PYTHON" -m pip install -r "$REPO_ROOT/integration/uniad/requirements-cu128.txt"
"$PYTHON" -m pip install setuptools==80.9.0

echo "Environment ready: $ENV_PREFIX"
echo "Next: $REPO_ROOT/scripts/build_carla_python310.sh"
