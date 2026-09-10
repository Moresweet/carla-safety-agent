# Tagged static proxies and distance-field lifetime

Target: this CARLA / Unreal 4.26 source build. Apply the accompanying patch from
the CARLA checkout after the existing tagging patches. It changes only four
annotation proxy constructors: static, spline, instanced and hierarchical.

Observed on 2026-09-10: Town04 → Town05 failed before VAD inference with
`FDistanceFieldVolumeTexture::IsValidDistanceFieldVolume` →
`FPrimitiveSceneShaderData` → `UpdateGPUSceneInternal` → `Render_CARLA`.
The same stack reproduced after an independent 20-frame sensor capture without
any driving model. The original native crash is preserved in
`Saved/Crashes/crashinfo-CarlaUE4-pid-14989-232A2CFD9FDD42F78F95F5E7ED914FAA`;
the second was caught by the parent GDB process in `.runtime/carla.log`.

Code inspection: `FStaticMeshSceneProxy` caches LOD0 `DistanceFieldData`.
`FDistanceFieldAsyncQueue::ProcessAsyncTasks` replaces that allocation while
recreating static-mesh component render states and defers deletion of the old
allocation. CARLA's annotation component is a separate `UPrimitiveComponent`
whose proxy inherits that cached pointer. Its `GetViewRelevance` already disables
shadow relevance. Retaining the parent's distance-field allocation for this
annotation-only proxy is unnecessary and creates a lifetime hazard.

The patch clears the inherited pointer in all four annotation constructors.
It does not change source mesh distance fields, visual mesh materials, model
weights, sensor placement, or the main scene's lighting. This is not a null
check on a potentially freed object; the annotation proxy never retains it.

Evidence boundary: the initial GDB frame-2 local was optimized/unreliable, so
it did not establish the exact dynamic proxy class at the fault. The stack and
code-path lifetime risk are established; do not claim a complete causal proof
or universal crash fix from compilation alone. Acceptance requires rebuilding
CarlaUE4Editor, launching a fresh native process and repeating map transitions,
independent sensor capture, real model runs and post-cleanup health checks.

The separate Town05 opponent-placement failure was a ground overlap at z=0;
0.5 m vehicle clearance succeeds at the same waypoint. It is not this native
segmentation fault.

Fresh-binary validation on 2026-09-10 passed the four bounded VAD/TCP map
transitions (Town04→Town05→Town04 for each), standalone capture, road texture
A/B and AD-MLP/UniAD Tiny/Base runs. Reports are recorded in
`docs/DEVELOPMENT_PLAN.md`; model frames and cleanup were checked independently.
This finite matrix did not reproduce the distance-field crash. A later VAD
missing-IMU Python failure is separately retained and investigated, not counted
as a native crash or hidden by these successful runs.
