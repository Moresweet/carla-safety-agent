# Local image validation — 2026-09-06

Image: `carla-safety-runtime:local`

Image digest: `sha256:68c826a06b694f2bc0aab07676c3326b957f7cdacdf44e424f3016e31991f975`

Validated on Linux x86_64, RTX 5070 Ti, driver 595.84. Native engine,
CARLA, ROS and Conda directories were not mounted into the running container.
Only project source, dependency/runtime volumes and X11 display access were mounted.

- Container health check passed; frontend and bridge served on 3000/8765.
- Town04 opened in a visible CARLA window. Cold map loading took 653 seconds;
  retain the stopped container to reuse generated shader caches.
- Compiled plugin/source and generated-asset checks passed.
- Real camera captures changed after green/magenta vehicle texture applications
  (3.74% of image pixels differed). Evidence: `runs/docker-smoke/`.
- All six ROS camera topics delivered nonempty images.
- RViz initialized OpenGL 4.6 and subscribed to configured topics. It emitted
  a first-run missing persistent-settings warning. The bounded ROS process also
  emitted a shutdown-context exception when terminated by the timeout.
- UniAD weights loaded on CUDA 12.8/PyTorch 2.7.1 (100,840,986 parameters).
- Town04 preset #24785 ran in closed loop. Telemetry advanced from frame 23
  to 42, with synchronized six-camera inputs, six-point predicted trajectories,
  and changing steering/throttle outputs. Speed changed from 2.04 to 4.94 m/s.
  The front camera endpoint returned HTTP 200 and 91,053 image bytes.
  The short run was deliberately stopped; this is not a completed-route score.
- Shell syntax, Git whitespace checks and the E2E benchmark unit test passed.

Existing engine asset-import/material warnings and Python deprecation warnings
remain; no fatal renderer crash was observed during these checks. Other GPUs,
towns and a second physical machine have not been validated. The captured CUDA
extensions target sm_120; see README for migration requirements.

No image was uploaded to a registry. Large temporary snapshot archives were
removed after image import to recover disk space; source files were untouched,
and the snapshot exporter can regenerate them. Hash/source manifests remain in
the recorded external snapshot directory.

GPU adaptation launcher follow-up: shell syntax and the disposable-container
`--check` passed on RTX 5070 Ti, detecting `12.0` and nvcc `sm_120` support.
The full forced rebuild/derived-image path has not yet been run; no second-GPU
compatibility claim follows from this preflight test.
