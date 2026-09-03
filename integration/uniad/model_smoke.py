#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from mmcv import Config
from mmcv.models import build_model
from mmcv.utils import load_checkpoint


def main() -> int:
    parser = argparse.ArgumentParser(description="Load UniAD-Tiny and move it to CUDA")
    parser.add_argument("--zoo", default="/home/moresweet/Data/e2e/Bench2DriveZoo")
    args = parser.parse_args()
    zoo = Path(args.zoo).resolve()
    config_path = zoo / "adzoo/uniad/configs/stage2_e2e/tiny_e2e_b2d.py"
    checkpoint_path = zoo / "ckpts/uniad_tiny_b2d.pth"
    cfg = Config.fromfile(str(config_path))
    cfg.model["motion_head"]["anchor_info_path"] = str(
        zoo / cfg.model["motion_head"]["anchor_info_path"])
    model = build_model(cfg.model, train_cfg=cfg.get("train_cfg"), test_cfg=cfg.get("test_cfg"))
    load_checkpoint(model, str(checkpoint_path), map_location="cpu", strict=True)
    model.cuda().eval()
    allocated = torch.cuda.memory_allocated()
    report = {
        "model": type(model).__name__,
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "checkpoint": str(checkpoint_path),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "device": torch.cuda.get_device_name(0),
        "capability": list(torch.cuda.get_device_capability(0)),
        "allocated_bytes": allocated,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
