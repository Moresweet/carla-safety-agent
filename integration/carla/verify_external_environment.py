#!/usr/bin/env python3
"""Verify reproducibility-critical files outside this repository."""
from argparse import ArgumentParser
from pathlib import Path


CHECKS = {
    "Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/CarlaGameModeBase.cpp": (
        'M_CarlaBuildingRuntime.M_CarlaBuildingRuntime'),
    "Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Actor/StaticMeshFactory.cpp": (
        'TEXT("scale_x")'),
    "Unreal/CarlaUE4/Plugins/Carla/Source/Carla/OpenDrive/OpenDriveGenerator.cpp": (
        'MeshData.UV0'),
}

ASSETS = (
    "Unreal/CarlaUE4/Content/Carla/Static/Car/4Wheeled/Tesla/Materials/M_CarlaLiveryRuntime.uasset",
    "Unreal/CarlaUE4/Content/Carla/Static/Car/4Wheeled/Tesla/Materials/MI_CarExterior_TeslaM3.uasset",
    "Unreal/CarlaUE4/Content/Carla/Static/Car/4Wheeled/Tesla/SM_TeslaM3_v2.uasset",
    "Unreal/CarlaUE4/Content/Carla/Static/GenericMaterials/RoadPainterMaterials/M_CarlaRoadRuntime.uasset",
    "Unreal/CarlaUE4/Content/Carla/Static/Building/Materials/M_CarlaBuildingRuntime.uasset",
)


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--carla-root", type=Path, default=Path("/home/moresweet/carla"))
    root = parser.parse_args().carla_root
    failures = []
    for relative, marker in CHECKS.items():
        path = root / relative
        if not path.is_file() or marker not in path.read_text(errors="replace"):
            failures.append(f"missing source marker: {path}: {marker}")
    for relative in ASSETS:
        path = root / relative
        if not path.is_file():
            failures.append(f"missing generated asset: {path}")
    if failures:
        print("External environment verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"External environment verified: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
