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

### Versioned pedestrian clothing slots

After the studio material runtime patch, apply and build
[`carla/studio-pedestrian-slot-material.patch`](carla/studio-pedestrian-slot-material.patch).
This keeps the verified walker pants slot on its clothing base rather than
vehicle paint; [scope and native verification](carla/studio-pedestrian-slot-material.md).

### Collision sensor lifecycle guard

`carla/tagged-parent-render-state.patch` subscribes skeletal annotation components
to the parent's MarkRenderStateDirty notification, immediately retires their
borrowed-resource proxy before parent recreation, and reuses the existing delayed
proxy recreation. OnUnregister removes the delegate. Apply after the tagged
skeletal refresh guard with `git apply --recount`, then rebuild the editor. This
must be validated against both capture teardown and material edits; it is not a
claim that every native resource lifetime path is protected.

`carla/tagged-skeletal-destroy-order.patch` changes ActorDispatcher destruction:
registered skeletal annotation components are unregistered and queued render
work is flushed before the parent actor releases its MeshObject. If actor
destruction fails, those components are registered again. This guards CARLA RPC
destruction, not arbitrary external engine destruction or map teardown. Apply
with `git apply --recount` after checking it, then rebuild CarlaUE4Editor.

`carla/collision-sensor-lifecycle.patch` modifies only CollisionSensor.h/cpp. It
unbinds the previous owner's hit delegate before reassignment and EndPlay, and
rejects callbacks during destruction before the base sensor closes its stream.
Apply from the CARLA source checkout with `git apply --recount --check` followed
by `git apply --recount`, then rebuild `make CarlaUE4Editor` from Unreal/CarlaUE4.
This addresses a concrete lifecycle gap; full collision-capture regression is
required before treating a particular native crash as resolved.

For an already-dead native editor, `scripts/restart_carla_native.sh --after-crash`
refuses a live UE4Editor and skips the impossible live scene save. It retains
persisted scenes and datasets but cannot recover unsaved in-memory state.

`CSA_NATIVE_DEBUG=1 scripts/restart_carla_native.sh --after-crash` launches the
native editor as a GDB child when attaching is restricted. It records thread
backtraces in `.runtime/carla.log` on a stop, skips the known nonfatal startup
SIGTRAP ensures, and retains the actual inferior PID for lifecycle management.
Crash recovery checks the local journal's live worker identity without relying
on an HTTP bridge that may itself be waiting on the dead simulator.

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

The Mercedes Coupe 2020 and Mini Cooper S 2021 skeletal meshes trigger the
UE4 FBX exporter crash. Their browser previews are therefore exported from the
matching parked static meshes with `export_missing_vehicle_preview_meshes.py`.
Convert material slot 0 and select the `LOD2` node with the optional node suffix
argument supported by `tools/fbx_mesh_to_json.cpp`. This changes no CARLA asset;
the generated web meshes are committed in this repository.

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
- The unified launcher resolves large-map directory layouts such as
  `Content/Carla/Maps/Town12/Town12.umap`; `CARLA_MAP=Town12` therefore starts
  `/Game/Carla/Maps/Town12/Town12` instead of the invalid flat-map path.
- The editor is launched with `r.GPUScene 0` in the existing low-quality
  research profile. UE4.26 otherwise races skeletal-proxy transform updates
  with Town12 distance-field/GPU-scene updates while preset actors activate;
  physics, CARLA sensors, semantic tags and evaluator logic remain enabled.
- UniAD evaluator process groups are recorded in `.runtime/uniad.pid` so the
  unified stop script also terminates an active closed-loop run.

No files under Unreal Engine itself have been modified. Temporary validation
scripts and screenshots under `/tmp` or `work/` are not required at runtime.

## End-to-end driving targets

External UniAD evaluation sources and weights are kept outside the repository:

| Path | Source / version |
| --- | --- |
| `/home/moresweet/Data/e2e/Bench2DriveZoo` | `Thinklab-SJTU/Bench2DriveZoo`, branch `uniad/vad-0.0.4`, commit `d9caa0af805ec3c435533aa268e2723d80c20017` |
| `/home/moresweet/Data/e2e/Bench2DriveZoo/ckpts/uniad_tiny_b2d.pth` | Official UniAD-Tiny checkpoint; 872547048 bytes; SHA-256 `de4396893c0a48a324fad4b87e4e5010a0eca22663ad434d0cf7c89c9bb5b7cc` |
| `/home/moresweet/Data/e2e/Bench2Drive` | External preset-route evaluator; local compatibility changes are reproducible from `integration/bench2drive/` |

The UniAD implementation commit remains pinned. The native project executor
does not require the Bench2Drive evaluator, ScenarioRunner, XML routes, runtime
symlinks, or modifications to an external evaluation repository.

The local Bench2DriveZoo clone has one source compatibility change recorded in
`integration/uniad/torch-2.7-dispatch.patch`: MMCV's retired `Tensor.type()`
dispatch call is replaced with `Tensor.scalar_type()` for PyTorch 2.7.

`integration/uniad/live-model-telemetry.patch` adds frame-boundary evidence
publication to the external UniAD adapter. It exports the actual six RGB
camera tensors consumed by UniAD, IMU/GNSS/speed inputs, the predicted
`sdc_traj` in ego coordinates, and the downstream PID control values. The
patch is observational: it does not alter model inputs, trajectory inference,
or vehicle control.

The CARLA source tree has Python 3.10 wheel-build compatibility changes,
recorded in `integration/uniad/carla-python310-conda-flags.patch`. It prevents
the UE4 Clang toolchain from treating Conda's unsupported GCC optimization flag
as a fatal error and lets the wheel build select a toolchain explicitly. The
CARLA setup script also pins the requested Boost.Python version instead of
silently selecting the host's Python 3.14 configuration. These changes do not
alter CARLA runtime behavior or RPC messages.

The external preset-route evaluator applies
`integration/bench2drive/reuse-current-world.patch`. It reuses the connected
CARLA world when the requested town is already loaded. This prevents a second
same-town preset selection from rebuilding Town12's renderer state and avoids
the UE4 distance-field/GPU-scene crash observed during redundant world loads.
The project preset launcher also pins `SCENARIO_RUNNER_ROOT` to the external
ScenarioRunner checkout. Without it the evaluator searches its working
directory, silently skips named scenarios such as `ParkingCutIn`, and produces
a route with no adversarial actors.

Miniconda is installed at `/home/moresweet/Data/e2e/miniconda3`; the tested
environment is `/home/moresweet/Data/e2e/miniconda3/envs/uniad-cu128`. The
matching source-built wheel is
`/home/moresweet/carla/PythonAPI/carla/dist/carla-0.9.16-cp310-cp310-linux_x86_64.whl`.
Use `scripts/install_uniad_cu128.sh` and `scripts/build_carla_python310.sh` when
assembling a container image.

## Container verification

The container recipes, allowlisted snapshot exporter and launcher are under
`integration/docker/` and `scripts/docker_studio.sh`. The first snapshot was
created at `/home/moresweet/Documents/Codex/carla-docker-snapshot-20260906`.
The small final license/launcher overlay is at
`/home/moresweet/Documents/Codex/carla-docker-finalize-20260906`.
It records dependency archive SHA-256 hashes, installed package lists and diffs
of the actual external source trees. The temporary `.tar` build inputs were
removed after Docker imported them to recover disk space; regenerate them with
the snapshot script if rebuilding from the host installation. No native CARLA, UE, ROS or Conda
file is modified by this container assembly. Docker images/volumes and this
snapshot directory are the generated files outside the repository. GUI startup
keeps a display-specific `.runtime/docker.xauth` cookie file with mode 0600 in
the ignored local runtime directory. The initial test used `/tmp/csa-xauth.H2wMbe`.

The runtime keeps the old absolute prefixes inside the image for compiled code
and Conda compatibility. Application code is mounted at `/workspace`; neither
the original home directory nor original dependency directories are mounted.
The container runs as UID 1000 and has its own service PID/log volume.

Run `integration/carla/verify_external_environment.py` after image assembly.
It checks source markers, generated assets, and the expected project paths
without modifying the installation.
