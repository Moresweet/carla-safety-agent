# External Environment Changes

This file records every required change outside this repository. Keep it in
sync with `integration/carla/` so the host installation can be reproduced in a
container image.

## Source tree

CARLA source root used during development: `/home/moresweet/carla`.

| External file | Repository recipe | Purpose |
| --- | --- | --- |
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/CarlaGameModeBase.cpp` | `vehicle-skeletal-texture.patch` | Apply runtime textures to skeletal meshes and the `LiveryTexture` parameter. |
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Actor/StaticMeshFactory.cpp` | `static-mesh-factory-nonuniform-scale.patch` | Add independent X/Y/Z scale attributes for generated assets. |
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/OpenDrive/OpenDriveGenerator.cpp` | `opendrive-road-material.patch` | Preserve generated road UV/color data and assign the asphalt material. |
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/CarlaGameModeBase.cpp` | `road-runtime-texture.patch` (apply after `vehicle-skeletal-texture.patch`) | Switch `Road_Road_*` objects to the runtime-replaceable road material. |

Apply the patches from the CARLA source root and rebuild the editor target:

```bash
git apply --check /workspace/carla-safety-agent/integration/carla/vehicle-skeletal-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/vehicle-skeletal-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/road-runtime-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/static-mesh-factory-nonuniform-scale.patch
git apply /workspace/carla-safety-agent/integration/carla/opendrive-road-material.patch
make CarlaUE4Editor
```

## Generated Unreal assets

These binary assets live in the CARLA content tree and are generated rather
than copied into this repository:

| External asset | Generator |
| --- | --- |
| `Content/Carla/Static/Car/4Wheeled/Tesla/Materials/M_CarlaLiveryRuntime.uasset` | `install_tesla_livery_material.py` |
| `Content/Carla/Static/Car/4Wheeled/Tesla/Materials/MI_CarExterior_TeslaM3.uasset` (parent updated) | `install_tesla_livery_material.py` |
| `Content/Carla/Static/Car/4Wheeled/Tesla/SM_TeslaM3_v2.uasset` (slot 5 updated) | `install_tesla_livery_material.py` |
| `Content/Carla/Static/GenericMaterials/RoadPainterMaterials/M_CarlaRoadRuntime.uasset` | `install_road_runtime_material.py` |

Generate assets with the same UE build used to run CARLA:

```bash
UE4Editor-Cmd /opt/carla/Unreal/CarlaUE4/CarlaUE4.uproject \
  -run=pythonscript \
  -script=/workspace/carla-safety-agent/integration/carla/install_tesla_livery_material.py \
  -unattended -nop4 -nosplash -nullrhi
```

Run the same command with `install_road_runtime_material.py` to generate
`M_CarlaRoadRuntime`, then rebuild after applying `road-runtime-texture.patch`.

## Runtime services

- CARLA RPC: `127.0.0.1:2000`
- Surface Studio: `127.0.0.1:3000`
- Texture bridge: `127.0.0.1:8765`
- Python dependencies: the CARLA Python module and Pillow
- Frontend runtime: Node.js and pnpm

No files under Unreal Engine itself have been modified. Temporary validation
scripts and screenshots under `/tmp` or `work/` are not required at runtime.

## Container verification

Run `integration/carla/verify_external_environment.py` after image assembly.
It checks source markers, generated assets, and the expected project paths
without modifying the installation.
