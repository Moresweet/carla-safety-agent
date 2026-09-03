#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path


EXPECTED = {
    "Bench2Drive": "7ec25d1c9f7522d923ce5f3420986cef1cb2d956",
    "Bench2DriveZoo": "d9caa0af805ec3c435533aa268e2723d80c20017",
}
CHECKPOINT_BYTES = 872_547_048
CHECKPOINT_SHA256 = "de4396893c0a48a324fad4b87e4e5010a0eca22663ad434d0cf7c89c9bb5b7cc"


def git_head(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True,
            stderr=subprocess.DEVNULL, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the local UniAD closed-loop target")
    parser.add_argument("--root", default="/home/moresweet/Data/e2e")
    parser.add_argument("--carla-port", type=int, default=2000)
    parser.add_argument("--hash-checkpoint", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    checkpoint = root / "Bench2DriveZoo/ckpts/uniad_tiny_b2d.pth"
    repos = {name: {"path": str(root / name), "head": git_head(root / name), "expected": commit}
             for name, commit in EXPECTED.items()}
    packages = {name: importlib.util.find_spec(name) is not None
                for name in ("torch", "carla", "cv2", "mmcv")}
    cuda = None
    if packages["torch"]:
        import torch
        cuda = {"torch": torch.__version__, "available": torch.cuda.is_available(),
                "runtime": torch.version.cuda,
                "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                "capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None}
    profile = sys.version_info[:2] == (3, 10)
    cuda_profile = bool(cuda and cuda["available"] and cuda["runtime"] == "12.8")
    report = {
        "python": sys.version.split()[0],
        "supported_python": profile,
        "nvcc": shutil.which("nvcc") or str(Path(sys.prefix) / "bin/nvcc")
        if (Path(sys.prefix) / "bin/nvcc").is_file() else None,
        "repositories": repos,
        "checkpoint": {"path": str(checkpoint), "exists": checkpoint.is_file(),
                       "bytes": checkpoint.stat().st_size if checkpoint.is_file() else 0,
                       "expected_bytes": CHECKPOINT_BYTES,
                       "expected_sha256": CHECKPOINT_SHA256,
                       "sha256": sha256(checkpoint) if args.hash_checkpoint else None},
        "packages": packages,
        "cuda": cuda,
        "carla_rpc_open": port_open("127.0.0.1", args.carla_port),
    }
    report["ready"] = (
        report["supported_python"] and all(packages.values())
        and checkpoint.is_file() and checkpoint.stat().st_size == CHECKPOINT_BYTES
        and all(v["head"] == v["expected"] for v in repos.values())
        and cuda_profile
    )
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
