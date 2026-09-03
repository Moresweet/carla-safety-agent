# UniAD closed-loop target

This integration treats UniAD as a system under test. The scenario generator
searches for difficult interactions, while the official Bench2Drive adapter
provides six-camera inference and CARLA control. Bench2Drive output is converted
to a failure-first ranking for replay and scenario minimization.

## Pinned external sources

- Bench2Drive `0.0.4`: `7ec25d1c9f7522d923ce5f3420986cef1cb2d956`
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
scripts/run_uniad_target.sh
PYTHONPATH=src python tools/uniad_results.py \
  runs/uniad/bench2drive.json --output runs/uniad/failure-report.json
```

Use `ROUTES=/absolute/path/to/one-route.xml` for a short smoke run. A campaign
should generate a small route/scenario batch, evaluate UniAD, rank failures,
then mutate the highest-ranked scenario near its failure boundary.

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
