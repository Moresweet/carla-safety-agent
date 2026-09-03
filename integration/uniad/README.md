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
scripts/run_uniad_target.sh --doctor
scripts/run_uniad_target.sh
PYTHONPATH=src python tools/uniad_results.py \
  runs/uniad/bench2drive.json --output runs/uniad/failure-report.json
```

Use `ROUTES=/absolute/path/to/one-route.xml` for a short smoke run. A campaign
should generate a small route/scenario batch, evaluate UniAD, rank failures,
then mutate the highest-ranked scenario near its failure boundary.

## Compatibility boundary

The official Zoo environment pins Python 3.8 and builds CUDA extensions. CARLA
0.9.15 is the published benchmark target. A source-built CARLA server may be
used only after its RPC protocol and maps have been verified against the 0.9.15
Python client. Do not mix the existing Python 3.14 CARLA API into the UniAD
environment.

The workstation's RTX 5070 Ti requires a CUDA/PyTorch build that includes its
GPU architecture. Consequently, blindly installing the official CUDA 11.8
recipe is not considered a valid reproduction. `doctor.py` fails closed until
Python, CUDA, MMCV, CARLA API, pinned sources and checkpoint are all present.
