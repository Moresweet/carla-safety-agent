# Portable CARLA research runtime

This image captures the locally compiled UE4.26/CARLA installation, including
modified plugin binaries and generated material/map assets. It also contains
ROS 2 Lyrical, RViz, Python 3.14 for the bridge, the Python 3.10/CUDA 12.8 UniAD
environment, model weights, and pinned frontend dependencies. Application and
ROS bridge source are bind-mounted at `/workspace`, so normal edits need no
image rebuild. Evaluation outputs remain in the mounted project's `runs/`.

## Build on the original workstation

```bash
docker build -f integration/docker/Dockerfile.base -t carla-safety-base:26.04 integration/docker
python3 integration/docker/snapshot.py /path/with/space/csa-snapshot
docker build -t carla-safety-runtime:local /path/with/space/csa-snapshot
```

Snapshot directories are created once, with archive SHA-256 hashes and local
source diffs under `manifest/`. The script never archives a whole home directory,
host credentials, Git metadata, shader caches, or build intermediate directories.
Original internal prefixes are retained for binary/Conda compatibility; these
are paths **inside the image**, not required paths on the destination machine.
This is a binary runtime snapshot, not a complete clean-source rebuild SDK.
The original source patches and material generation recipes remain in
`integration/ENVIRONMENT_CHANGES.md`; generated binary assets are in the image.

The base pins Ubuntu by digest. Apt repositories can change; preserve the final
image with `docker save` for exact reproduction. Snapshotting must take place
while no dependency installation, engine build, or asset editing is in progress.
Allow enough disk for both archives and image/build cache (roughly four times
the selected payload). Do not run Docker prune on shared installations.

## Transfer and run

```bash
docker save carla-safety-runtime:local | gzip > carla-safety-runtime.tar.gz
# On the destination Linux x86_64 workstation:
docker load -i carla-safety-runtime.tar.gz
git clone git@github.com:Moresweet/carla-safety-agent.git
cd carla-safety-agent
bash scripts/docker_studio.sh start
bash scripts/docker_studio.sh check
bash scripts/docker_studio.sh ros
bash scripts/docker_studio.sh rviz
bash scripts/docker_studio.sh stop
```

The destination needs Docker Compose, an NVIDIA GPU/compatible driver and
NVIDIA Container Toolkit. CUDA user libraries are bundled; kernel/GPU drivers
come from the destination host. X11/XWayland plus `xauth` is required for visible
CARLA/RViz windows; use `HEADLESS=1` for offscreen CARLA. No privileged container,
Docker socket mount, or global `xhost +` is used.

The captured custom UniAD CUDA extensions were compiled for `sm_120` (RTX 50
series), not every NVIDIA GPU. On a different architecture, rebuild the
extensions inside a GPU-enabled container using its bundled toolchain before
evaluating. For example, from a container shell, set `CUDA_HOME` to the UniAD
environment prefix, put its `bin` directory on `PATH`, set `CC`/`CXX` to its
Conda GCC/G++ binaries, and set `TORCH_CUDA_ARCH_LIST` for the destination GPU.
Then run `python setup.py build_ext --inplace --force` with the UniAD Python
from the bundled `Bench2DriveZoo` directory. Re-run the actual model smoke test
and save that derived image. Cross-GPU operation is not validated by a successful
`torch.cuda.is_available()` result alone.

The container runs as UID 1000, matching this workstation. The mounted checkout
must be writable by that UID; adapt ownership/ACLs deliberately when migrating
to a host with another user ID. No launcher changes host checkout ownership.

Open `http://localhost:3000/`. Host networking supports the current loopback-only
frontend/bridge and ROS DDS; ports 2000–2002, 3000, 8765 and 8000 must not conflict
with an existing test. Stop the native installation yourself before starting
the container. The stop command preserves this project's containers and their
compiled shader caches for fast restarts. To intentionally remove containers,
use `docker compose -f integration/docker/compose.yaml down`; a new container
will have to regenerate shader caches.

Frontend `node_modules` and service state have dedicated Docker volumes; host
dependencies and PID files are not overwritten. The image's dependencies seed
the initially empty frontend volume. If the dependency lock changes, rebuild
the dependency payload and create a new volume. Logs are available using
`bash scripts/docker_studio.sh logs`. Use `docker compose -f
integration/docker/compose.yaml exec studio bash` for a shell.

Compose uses the checkout's `integration/docker/entrypoint.sh`, so launcher fixes
also work without rebuilding UE or the image. Cold shader caches can take
several minutes to populate; startup allows 900 seconds by default.

With a running container, render and ROS checks are available as:

```bash
docker compose -f integration/docker/compose.yaml exec -T studio \
  /opt/csa/entrypoint.sh python3 /workspace/integration/docker/smoke.py --keep-vehicle
docker compose -f integration/docker/compose.yaml exec -T studio bash -c \
  'source /opt/ros/lyrical/setup.bash; PYTHONPATH="$CARLA_PYTHONPATH:$PYTHONPATH" python3 /workspace/integration/docker/ros_smoke.py'
```

The first command leaves its test vehicle for the ROS check. Delete that test
vehicle through the object manager when finished. Evidence is written to
`runs/docker-smoke/` in the checkout. These tests create actors and should be
run in an idle world, not during another evaluation.

Keep this image private unless you have checked redistribution terms for Unreal
Engine, CARLA assets, model code and weights. Source license files are preserved.
Building locally does not publish the image to any registry.

References: [Docker GPU support](https://docs.docker.com/compose/how-tos/gpu-support/),
[bind mounts](https://docs.docker.com/engine/storage/bind-mounts/),
[ROS Lyrical binaries](https://docs.ros.org/en/lyrical/Installation/Alternatives/Ubuntu-Install-Binary.html).
