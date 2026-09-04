# UniAD closed-loop target

This integration treats UniAD as a replaceable system under test. The project
owns natural-language compilation, ScenarioSpec, CARLA construction, six-camera
sensor synchronization, route execution, live editing and safety evaluation.
Only the official UniAD implementation and checkpoint remain external.

## Project-owned runtime boundary

`carla_safety_agent.native_executor` consumes the exact JSON emitted by Generate
Scene. It constructs the world, route, actors and sensors without an external
benchmark evaluator. `evaluation_control` applies UI commands on synchronous
frame boundaries, so scene editing remains available during model execution.

## Pinned external sources

- Bench2DriveZoo `uniad/vad-0.0.4`: `d9caa0af805ec3c435533aa268e2723d80c20017`
- Model: official `uniad_tiny_b2d.pth` under `Bench2DriveZoo/ckpts`, 872547048
  bytes, SHA-256 `de4396893c0a48a324fad4b87e4e5010a0eca22663ad434d0cf7c89c9bb5b7cc`

The default external root is `/home/moresweet/Data/e2e`. It is intentionally
outside this repository because model weights and upstream sources are large.

## Commands

```bash
source /home/moresweet/Data/e2e/miniconda3/bin/activate uniad-cu128
scripts/run_uniad_target.sh --doctor
python integration/uniad/model_smoke.py
SCENARIO=.runtime/generated-scenarios/my-scenario.json scripts/run_uniad_target.sh
```

The web UI's “Test this scene with UniAD” action performs compilation and launch
in one step. The output uses `carla-safety-evaluation/0.1` JSON.

## Compatibility boundary

The official Zoo environment pins Python 3.8 and older CUDA extensions. This
workstation profile uses Python 3.10 and a Python wheel built from the exact
local CARLA source revision. Do not mix the existing Python 3.14 CARLA API or
the generic PyPI wheel into the UniAD environment.

The workstation's RTX 5070 Ti requires a CUDA/PyTorch build that includes its
GPU architecture. Consequently, blindly installing the official CUDA 11.8
recipe is not considered a valid reproduction. `doctor.py` fails closed until
Python, CUDA, MMCV, CARLA API, pinned sources and checkpoint are all present.

The tested compatibility environment is named `uniad-cu128`: Python 3.10,
PyTorch 2.7.1+cu128, CUDA toolkit 12.8 and GCC 11. Its Conda packages are in
`environment-cu128.yml`; Python dependencies with obsolete upstream pins
updated for Python 3.10 are in `requirements-cu128.txt`. Setuptools is held at
80.9.0 because the upstream visualization dependency still imports
`pkg_resources`.

Create the complete environment with `scripts/install_uniad_cu128.sh`. If the
CARLA source is rebuilt or its revision changes, rerun
`scripts/build_carla_python310.sh`. The latter builds a matching Boost.Python
library, creates the CPython 3.10 wheel and installs it into `uniad-cu128`.
