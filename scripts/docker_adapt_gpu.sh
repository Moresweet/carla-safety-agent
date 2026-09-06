#!/usr/bin/env bash
# Build a derived image without touching the running studio or host dependencies.
set -Eeuo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:---build}
[[ "$mode" == --build || "$mode" == --check ]] || { echo 'Usage: docker_adapt_gpu.sh [--check|--build]'; exit 2; }
base=${CSA_BASE_IMAGE:-carla-safety-runtime:local}
target=${CSA_GPU_IMAGE:-carla-safety-runtime:gpu-local}
if [[ "$mode" == --check ]]; then
  exec docker run --rm --gpus all --network none --mount "type=bind,src=$root,dst=/workspace,readonly" \
    -e TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-}" --entrypoint bash "$base" \
    /workspace/integration/docker/rebuild_gpu.sh --check
fi
[[ "$target" != "$base" ]] || { echo 'Use a separate output image tag'; exit 2; }
if docker image inspect "$target" >/dev/null 2>&1; then
  echo "Output tag exists: $target. Choose a new CSA_GPU_IMAGE tag."; exit 2
fi
container=$(docker create --gpus all --network none --shm-size 4g \
  --mount "type=bind,src=$root,dst=/workspace,readonly" \
  -e TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-}" -e MAX_JOBS="${MAX_JOBS:-2}" \
  --entrypoint bash "$base" /workspace/integration/docker/rebuild_gpu.sh --build)
echo "Build container: $container (retained for inspection)"
docker start --attach "$container"
code=$(docker inspect --format '{{.State.ExitCode}}' "$container")
[[ "$code" == 0 ]] || { echo "Build failed ($code); no image committed"; exit 1; }
# Restore normal runtime startup rather than inheriting the build command.
docker commit --change 'ENTRYPOINT ["/usr/bin/tini","-g","--","/opt/csa/entrypoint.sh"]' \
  --change 'CMD ["studio"]' "$container" "$target"
echo "Created $target; build container retained: $container"
