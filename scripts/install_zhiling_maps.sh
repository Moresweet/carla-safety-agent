#!/usr/bin/env bash
set -Eeuo pipefail
CARLA_ROOT="${CARLA_ROOT:-/home/moresweet/carla}"
DATA_ROOT="${DATA_ROOT:-/home/moresweet/Data}"
CONTENT_ROOT="$CARLA_ROOT/Unreal/CarlaUE4/Content"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for archive in "$DATA_ROOT/zhilingMap/ngsim_ZhiLing.zip" "$DATA_ROOT/zhilingMap/highd_ZhiLing.zip"; do
  [[ -f "$archive" ]] || { echo "Missing map archive: $archive" >&2; exit 1; }
  unzip -n "$archive" -d "$CONTENT_ROOT"
done
mkdir -p "$CONTENT_ROOT/ZhiLing/Config"
cp "$ROOT_DIR/integration/datasets/ZhiLing.Package.json" "$CONTENT_ROOT/ZhiLing/Config/ZhiLing.Package.json"
find "$CONTENT_ROOT/ZhiLing/Plugin_Import/Maps" -maxdepth 1 -name '*.umap' -printf '%f\n' | sort
echo "Installed under $CONTENT_ROOT/ZhiLing (restart UE4Editor to refresh the asset registry)."
