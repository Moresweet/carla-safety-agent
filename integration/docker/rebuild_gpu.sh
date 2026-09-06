#!/usr/bin/env bash
# Run in a disposable GPU-enabled container, never the native installation.
set -Eeuo pipefail
[[ -f /.dockerenv ]] || { echo 'Run inside the runtime Docker image.' >&2; exit 2; }
mode=${1:---build}
[[ "$mode" == --build || "$mode" == --check ]] || { echo 'Usage: rebuild_gpu.sh [--check|--build]'; exit 2; }
py=${UNIAD_PYTHON:?Missing UNIAD_PYTHON}
zoo=${E2E_ROOT:?Missing E2E_ROOT}/Bench2DriveZoo
export CUDA_HOME="$(dirname "$(dirname "$py")")"
export PATH="$CUDA_HOME/bin:$PATH"
export CC="$CUDA_HOME/bin/x86_64-conda-linux-gnu-gcc"
export CXX="$CUDA_HOME/bin/x86_64-conda-linux-gnu-g++"
export MAX_JOBS=${MAX_JOBS:-2}
unset PYTHONPATH
[[ -x "$CC" && -x "$CXX" && -x "$CUDA_HOME/bin/nvcc" && -f "$zoo/setup.py" ]] || { echo 'Bundled build toolchain/source missing'; exit 2; }
export TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST:-$("$py" -c 'import torch; assert torch.cuda.is_available(), "NVIDIA GPU unavailable"; print(";".join(sorted({"%d.%d" % torch.cuda.get_device_capability(i) for i in range(torch.cuda.device_count())})))')}
"$py" - <<'PY'
import os, platform, subprocess, torch
from torch.utils.cpp_extension import _get_cuda_arch_flags
assert platform.machine() == 'x86_64', 'This image targets Linux x86_64'
assert torch.cuda.is_available(), 'GPU driver/container runtime unavailable'
flags = _get_cuda_arch_flags()
supported = subprocess.check_output([os.environ['CUDA_HOME']+'/bin/nvcc', '--list-gpu-code'], text=True)
for flag in flags:
    code = flag.split('code=')[-1]
    if code.startswith('sm_') and code not in supported.split():
        raise SystemExit(f'Bundled CUDA compiler does not support {code}; a different toolchain/image is required')
print('GPUs:', [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
print('Architecture list:', os.environ['TORCH_CUDA_ARCH_LIST'])
print('Compiler flags:', flags)
x = torch.ones(8, device='cuda'); assert x.sum().item() == 8
PY
[[ "$mode" != --check ]] || exit 0
cd "$zoo"
# Fresh intermediates avoid reusing objects compiled for the original GPU.
build_dir=$(mktemp -d /tmp/csa-gpu-build.XXXXXX)
echo "Build directory: $build_dir"
"$py" setup.py build_ext --inplace --force --build-temp "$build_dir"
"$py" - <<'PY'
import torch
from mmcv.ops import nms
boxes = torch.tensor([[0,0,10,10],[0,0,10,10]], dtype=torch.float32, device='cuda')
scores = torch.tensor([0.9,0.8], device='cuda')
_, indices = nms(boxes, scores, 0.5)
torch.cuda.synchronize()
assert indices.tolist() == [0], indices
print('Compiled CUDA NMS kernel passed')
PY
"$py" /workspace/integration/uniad/model_smoke.py --zoo "$zoo"
echo 'Build and smoke checks passed. Run a closed-loop test before accepting this image.'
