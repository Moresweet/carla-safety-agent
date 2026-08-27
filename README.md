# CARLA Safety Agent

An original, risk-directed scenario generation agent for CARLA 0.9.16. It borrows
the useful architectural idea of task packets, adapters, execution and evidence
from GameFactory-3A, but defines a safety-specific scenario model, sampler,
oracles and CARLA runtime boundary.

## What the MVP does

- Generates deterministic `cut_in`, `hard_brake`, and `occluded_crossing` families.
- Compiles Chinese or English descriptions into a reviewable scenario JSON file.
- Covers an initial NHTSA-aligned subset: rear-end, lead-vehicle lane change,
  vulnerable road user, crossing path, and merge.
- Emits an explicit CARLA build plan before touching the simulator.
- Builds and renders an ego chase-camera sequence on demand.
- Generates collision-enabled fallen-cargo assets from structured dimensions,
  mass, placement and multiplicity instead of requiring a pre-authored CARLA prop.
- Compiles line and arc sequences into a new OpenDRIVE road world at runtime.
- Textures generated roads with CARLA's asphalt material and populates them with
  deterministic buildings, trees, pedestrians and background vehicles.
- Captures synchronized RGB, logarithmic depth, semantic segmentation and LiDAR evidence.
- Biases samples toward parameter boundaries instead of producing ordinary traffic.
- Runs CARLA in synchronous fixed-step mode.
- Records distance/TTC traces and collision events.
- Ranks runs by risk and saves fully reproducible scenario specifications.
- Imports no CARLA code during offline generation or testing.

## Use on this machine

The existing CARLA virtual environment has been verified to load `carla.Client`.
Use it directly; a native-extension wheel cannot be imported by merely adding
the compressed `.whl` file to `PYTHONPATH`.

```bash
cd /home/moresweet/Documents/Codex/2026-08-26/gi/outputs/carla-safety-agent
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python -m carla_safety_agent.cli --help
```

## Generate scenarios offline

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python -m carla_safety_agent.cli generate \
  --family hard_brake --map Town04 --count 25 --seed 42 \
  --output runs/hard_brake/specs.json
```

## Natural language to build and render

Compile a description. Units are normalized to SI, and every unspecified
safety-relevant value is recorded as a warning and in provenance:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python \
  -m carla_safety_agent.cli from-text \
  '在 Town04 大雨夜间，自车以 72 km/h 跟随前车，前车以 36 km/h 行驶并突然急刹' \
  --seed 42 --output runs/demo/scenario.json
```

Validate the scenario and inspect the exact construction contract without
starting CARLA:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python \
  -m carla_safety_agent.cli build runs/demo/scenario.json \
  --output runs/demo/build-plan.json
```

With CARLA already running, build the actors, execute the interaction, and save
1280×720 PNG frames every five simulator frames:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python \
  -m carla_safety_agent.cli render runs/demo/scenario.json \
  --host 127.0.0.1 --port 2000 --timeout 120 \
  --output-dir runs/demo/evidence
```

Supported description cues include `追尾/急刹`, `前车变道`, `行人横穿/VRU`,
`交叉路径/路口横穿`, and `汇入/合流`, plus their English equivalents. A
description that contains no supported type or mixes multiple types fails
explicitly instead of silently guessing.

## Runtime-generated hazard assets

The first generated asset is a bundle of independently simulated metal pipes.
The compiler accepts descriptions such as:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python \
  -m carla_safety_agent.cli from-text \
  'Town04 高速公路前方 40 米有掉落货物，6 根金属管，自车速度 72 km/h' \
  --output runs/fallen-cargo/scenario.json
```

Each pipe is instantiated from engine primitive geometry with generated
non-uniform dimensions, pose, collision and mass. The resulting bundle is not a
pre-authored map prop and can be varied without importing another `.uasset`.

The CARLA source extension exposes non-uniform scale through the existing
`static.prop.mesh` RPC factory. Apply it at the CARLA repository root and rebuild
the editor target:

```bash
git apply /path/to/carla-safety-agent/integration/carla/static-mesh-factory-nonuniform-scale.patch
make launch
```

## Generate a new road environment

This description creates a new 200 m S-curve road instead of loading a Town map,
then places generated cargo on it:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python \
  -m carla_safety_agent.cli from-text \
  '生成一张双向四车道新地图，包含 S弯，前方 55 米有 8 根金属管掉落货物，自车速度 54 km/h' \
  --seed 88 --output runs/generated-s-curve/scenario.json

PYTHONPATH=src /home/moresweet/carla/.venv/bin/python \
  -m carla_safety_agent.cli render runs/generated-s-curve/scenario.json \
  --output-dir runs/generated-s-curve/evidence
```

The structured `generated_map.segments` list accepts `line` and constant-curvature
`arc` elements. Each element has its own length and curvature, allowing straight,
C-shaped and S-shaped roads to be composed without importing a map asset. The
run directory retains the generated `.xodr` file and sensor folders named
`frames`, `depth`, `semantic`, and `lidar`.

Generated environments are realistic by default. Asset counts are part of the
structured contract (`tree_count`, `building_count`, `pedestrian_count`, and
`traffic_vehicle_count`) and can be extracted from descriptions such as:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python \
  -m carla_safety_agent.cli from-text \
  '生成真实环境双向4车道S弯，有20棵树、8栋建筑、6名行人、6辆背景车，前车急刹' \
  --seed 27 --output runs/realistic/scenario.json
```

Apply `integration/carla/opendrive-road-material.patch` to the CARLA source and
rebuild `CarlaUE4Editor` to preserve generated UV coordinates and bind the
packaged asphalt material. Without this extension, dynamic OpenDRIVE roads use
the default white procedural-mesh material.

## ROS2 and RViz visualization

A standalone ROS2 package is provided in `ros2/carla_safety_visualization`. It
attaches visualization sensors to the current hero vehicle and publishes:

- `/carla/ego/rgb/image`
- `/carla/ego/depth/image`
- `/carla/ego/semantic/image`
- `/carla/ego/lidar/points`
- `/carla/ego/odometry`
- `/carla/map/road_markers`
- `map -> ego_vehicle` TF

The bridge also mounts a configurable six-camera surround rig: front,
front-left, front-right, rear, rear-left and rear-right. Each stream publishes
an image, calibrated `CameraInfo`, physical-link TF and ROS optical-frame TF.
The supplied RViz profile uses six ROS image panels, follows `ego_vehicle`, and
renders the CARLA road topology, LiDAR, odometry and TF in the central view.

On a machine with ROS2 and RViz installed:

```bash
mkdir -p ros_ws/src
ln -s "$PWD/ros2/carla_safety_visualization" ros_ws/src/
cd ros_ws
colcon build --symlink-install
source install/setup.bash
ros2 run carla_safety_visualization bridge
rviz2 -d src/carla_safety_visualization/rviz/carla_safety.rviz
```

The matching CARLA Python module must be available in the ROS2 environment.
The package has been built and run on this workstation with ROS 2 Lyrical. RGB,
depth, semantic, LiDAR, odometry, dynamic TF and static sensor TF were verified
with ROS CLI tools, and the supplied RViz configuration was opened successfully.
Load `/opt/ros/lyrical/setup.bash` before building or running on this machine.

## Interactive vehicle livery editor

`tools/livery-designer` is a local browser editor for converting an uploaded
PNG, JPEG or WebP image into a repeatable vehicle appearance atlas. It supports
positioned decals, tiled graphics and full-atlas coverage, then exports both a
PNG and `vehicle-appearance.json` placement contract. In decal mode the image
can be dragged directly on the atlas and resized with the mouse wheel.

The editor loads 9,266 body triangles exported from
`SM_TeslaM3_v2`, material slot 5, UV channel 0. A color-coded UV wireframe is
displayed separately from the exported texture, and the same mesh drives an
orbitable WebGL preview that updates with the atlas. The wireframe overlay is a
guide only and is never baked into the livery sent to CARLA.

```bash
cd tools/livery-designer
pnpm run dev
```

Start the local bridge in a second terminal with CARLA's Python module available:

```bash
PYTHONPATH=/path/to/carla/python/site-packages python3 tools/livery_bridge.py
```

To regenerate the web mesh after replacing the CARLA vehicle asset, first run
`integration/carla/export_tesla_uv_mesh.py` with UE4Editor-Cmd, then compile and
run `tools/fbx_mesh_to_json.cpp` against Unreal's bundled FBX SDK.

Install the dedicated full-color Tesla material once, before starting CARLA:

```bash
/path/to/UE4Editor-Cmd /path/to/CarlaUE4.uproject \
  -run=pythonscript \
  -script=/path/to/carla-safety-agent/integration/carla/install_tesla_livery_material.py \
  -unattended -nop4 -nosplash
```

`Apply live livery` sends the canvas directly to the running Tesla Model 3. The
compiled CARLA source must include
`integration/carla/vehicle-skeletal-texture.patch`, which extends the existing
texture RPC from static meshes to vehicle skeletal meshes and updates the
dedicated `LiveryTexture` parameter.

The material is bound before the vehicle is spawned. Runtime updates therefore
change only its texture parameter and do not replace a live skeletal material
slot, avoiding CARLA's tagged skeletal scene proxy `MeshObject` assertion.

The 2048 x 2048 base shown by the editor is exported from CARLA's actual Tesla
Model 3 bodywork texture asset, `M_Tesla_Bodywork_d_a`, rather than a hand-drawn
region approximation.

## Downhill occlusion scenario

The generated road model also supports a per-segment grade. This description
creates a continuous 5% downhill S-curve, three static concrete occluders and
dynamic fallen pipes:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python \
  -m carla_safety_agent.cli from-text \
  '生成双向四车道 S弯下坡新地图，混凝土护栏形成遮挡，前方 60 米有 6 根金属管掉落货物，自车速度 54 km/h' \
  --seed 99 --output runs/downhill-occlusion/scenario.json
```

The stable schema is in `schema/scenario.schema.json`. The interaction enum
names are project identifiers aligned to the five representative groups in
NHTSA DOT HS 813 073; they are not presented as official NHTSA software codes.

## Execute against CARLA

Start the existing CARLA server separately, then run:

```bash
PYTHONPATH=src /home/moresweet/carla/.venv/bin/python -m carla_safety_agent.cli run \
  runs/hard_brake/specs.json \
  --host 127.0.0.1 --port 2000 --output-dir runs/hard_brake/evidence
```

The output contains `results.json` sorted by risk plus a per-scenario trace.

The agent loop is: define a scenario family and parameter envelope, generate a
boundary-biased campaign, execute it through the narrow CARLA adapter, evaluate
each trace with explicit oracles, rank critical evidence, then use retained
specifications as the reproducible seed population for the next campaign. This
separation is intentional: an LLM may propose families and constraints, but it
does not invent simulator measurements or overwrite oracle evidence.

## Research extension path

The next layer should add full junction route-conflict geometry, generated
terrain and lane markings, OpenSCENARIO export, adaptive
search (cross-entropy/Bayesian/CMA-ES), minimisation of discovered failures, and
an ADS-under-test interface. Generated visual assets must remain separate from
ground-truth collision, semantic and dynamics assets.

## Safety interpretation

The included TTC is a constant-velocity online surrogate. It is intentionally
labelled and must not be treated as a formal RSS proof. A research claim should
name the tested ADS, Operational Design Domain, simulator version, seeds,
scenario distributions and oracle limitations.
