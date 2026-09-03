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
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/CarlaGameModeBase.cpp` | `building-runtime-texture.patch` (apply after the road patch) | Route BP_House16 wall slot 0 to the building runtime material. |
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/CarlaGameModeBase.cpp` | `pedestrian-clothing-texture.patch` (apply after the building patch) | Enumerate skeletal actors and route the verified walker clothing section to its runtime material. |
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/CarlaGameModeBase.cpp` | `hgv-livery-texture.patch` (apply last) | Route European HGV skeletal material slot 1 to its dedicated runtime livery material. |
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/CarlaGameModeBase.cpp` | `all-vehicle-livery-texture.patch` (apply after the HGV patch) | Detect each skeletal vehicle's actual bodywork material slot instead of assuming slot 5. |
| `Unreal/CarlaUE4/Plugins/Carla/Source/Carla/Game/TaggedComponent.{h,cpp}` and `CarlaGameModeBase.cpp` | `tagged-skeletal-refresh-guard.patch` (apply last) | Remove and flush the semantic skeletal proxy before material replacement, then rebuild it once to prevent transform/render-thread races. |

Apply the patches from the CARLA source root and rebuild the editor target:

```bash
git apply --check /workspace/carla-safety-agent/integration/carla/vehicle-skeletal-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/vehicle-skeletal-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/road-runtime-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/building-runtime-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/pedestrian-clothing-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/hgv-livery-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/all-vehicle-livery-texture.patch
git apply /workspace/carla-safety-agent/integration/carla/tagged-skeletal-refresh-guard.patch
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
| `Content/Carla/Static/Building/Materials/M_CarlaBuildingRuntime.uasset` | `install_building_runtime_material.py` |
| `Content/Carla/Static/Pedestrian/Materials/M_CarlaPedestrianClothingRuntime.uasset` | `install_pedestrian_clothing_material.py` |
| `Content/Carla/Static/Truck/European_HGV/M_CarlaHGVLiveryRuntime.uasset` | `install_hgv_livery_material.py` |
| `Content/Carla/Static/GenericMaterials/M_CarlaVehicleLiveryRuntime.uasset` | `install_vehicle_livery_material.py` |

Generate assets with the same UE build used to run CARLA:

```bash
UE4Editor-Cmd /opt/carla/Unreal/CarlaUE4/CarlaUE4.uproject \
  -run=pythonscript \
  -script=/workspace/carla-safety-agent/integration/carla/install_tesla_livery_material.py \
  -unattended -nop4 -nosplash -nullrhi
```

Run the same command with `install_road_runtime_material.py` to generate
`M_CarlaRoadRuntime`, then rebuild after applying `road-runtime-texture.patch`.
Run it once more with `install_building_runtime_material.py` to generate
`M_CarlaBuildingRuntime`, then rebuild after applying
`building-runtime-texture.patch`.
Run it again with `install_pedestrian_clothing_material.py` to create the
skeletal-mesh-compatible clothing material before applying the pedestrian
patch and rebuilding.
Run it with `install_hgv_livery_material.py` to create the European HGV UV0
bodywork material before applying `hgv-livery-texture.patch` and rebuilding.
Run it with `install_vehicle_livery_material.py` to create the shared UV0
skeletal vehicle material before applying `all-vehicle-livery-texture.patch`.

Browser UV/3D assets for the registered vehicle catalog are exported with
`export_vehicle_uv_catalog.py`. The generated JSON catalog and meshes are
stored under `tools/livery-designer/public/vehicle-mesh-catalog.json` and
`tools/livery-designer/public/vehicles/` so the browser never substitutes a
photograph for a successfully exported vehicle mesh.

The browser mesh is reproducibly exported from
`/Game/Carla/Static/Truck/European_HGV/SK_European_HGV` by
`export_hgv_uv_mesh.py`, then converted with `tools/fbx_mesh_to_json.cpp` using
material slot 1. Runtime thumbnail PNGs are cached under
`.runtime/thumbnails`; this cache is optional and can be regenerated.

## Runtime services

- CARLA RPC: `127.0.0.1:2000`
- Surface Studio: `127.0.0.1:3000`
- Texture bridge: `127.0.0.1:8765`
- Python dependencies: the CARLA Python module and Pillow
- Frontend runtime: Node.js and pnpm
- Unified launcher variables: `CARLA_ROOT`, `UE4_ROOT`, `CARLA_PYTHONPATH`,
  `NODE_BIN`, `PNPM_BIN`,
  `CARLA_MAP`, and `CARLA_PORT`; browser services use ports 3000 and 8765

No files under Unreal Engine itself have been modified. Temporary validation
scripts and screenshots under `/tmp` or `work/` are not required at runtime.

## Container verification

Run `integration/carla/verify_external_environment.py` after image assembly.
It checks source markers, generated assets, and the expected project paths
without modifying the installation.
