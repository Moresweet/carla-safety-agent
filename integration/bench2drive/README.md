# Bench2Drive end-to-end algorithms

The studio runs released Bench2DriveZoo agents against the official
Bench2Drive Leaderboard. Model repositories and checkpoints remain outside this
repository so they can be updated independently.

## Supported models

| Model | Official branch | Checkpoint | Cameras | Runtime evidence |
| --- | --- | --- | ---: | --- |
| UniAD-Tiny | `uniad/vad-0.0.4` | `uniad_tiny_b2d.pth` | 6 | cameras, plan, PID control |
| UniAD-Base | `uniad/vad-0.0.4` | `uniad_base_b2d.pth` | 6 | cameras, plan, PID control |
| VAD | `uniad/vad-0.0.4` | `vad_b2d_base.pth` | 6 | cameras, plan, PID control |
| TCP | `tcp/admlp` | `tcp_b2d.ckpt` | 3 | cameras, plan, PID control |
| AD-MLP | `tcp/admlp` | `admlp_b2d.ckpt` | 1 | camera, plan, PID control |

DriveAdapter and ThinkTwice are shown as published comparison baselines only.
Bench2DriveZoo does not publish runnable adapters and checkpoints for them, so
the studio deliberately reports `not_released` instead of claiming support.

## Runtime layout

Defaults can be overridden with environment variables:

```text
/home/moresweet/Data/e2e/Bench2Drive
/home/moresweet/Data/e2e/Bench2DriveZoo
/home/moresweet/Data/e2e/Bench2DriveZoo-tcp-admlp
/home/moresweet/Data/e2e/miniconda3/envs/uniad-cu128
```

`scripts/run_benchmark_preset.sh` selects the correct official adapter,
configuration, checkpoint and branch. The local wrappers in this directory add
the shared live-evidence contract and PyTorch 2.6 compatibility for the trusted
official AD-MLP Lightning checkpoint; they do not replace model inference.

Use `E2E_CHECK_ONLY=1` to validate wiring without launching CARLA:

```bash
E2E_CHECK_ONLY=1 ALGORITHM=vad ROUTES=/path/to/routes.xml ROUTE_ID=24785 \
  scripts/run_benchmark_preset.sh
```

The bridge treats a failed route record as a failed job even when the upstream
Leaderboard process exits with status zero.
