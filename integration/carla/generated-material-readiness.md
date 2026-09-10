# Generated material first-frame readiness (UE 4.26 editor runtime)

`generated-material-readiness.patch` applies on top of this project's existing
static mesh axis-scale extension. It does not change the Python RPC ABI.

Observed before the patch: a newly imported green Blender barrier displayed the
default gray material in the first preview, then green three seconds later.
Import exit code was zero. Evidence: `asset-import-1ffefb6325784dc6a0f93c34cf8494ba`.
Therefore successful disk import is not runtime shader readiness.

The native mesh factory now loads and validates the mesh before creating an
Actor. In `WITH_EDITOR` builds, meshes under `/Game/Carla/Static/Generated/` wait
for each actual material resource's `FinishCompilation()`, require a valid game
thread shader map, and flush queued render updates before exposing the Actor.
It does not call `FinishAllCompilation` or change materials on other assets.
Missing mesh/material resources and compilation failure reject creation.
Failed mesh assignment destroys the newly created, not-yet-registered Actor.

Local engine sources used: `MaterialShared.h` exposes `FinishCompilation` and
`HasValidGameThreadShaderMap`; `MaterialShared.cpp` waits for this resource's
unfinished shader-map IDs. UE 4.26 uses the `UStaticMesh::StaticMaterials` field,
not the newer `GetStaticMaterials` accessor. The first build caught that API
difference; the corrected ten-action build passed (`material-ready-build-fT5a2f.log`).

Build CarlaUE4Editor and start a fresh native process; an already-running editor
does not load the new binary. Save/restore the current studio scene around the
restart. Run `tools/regression_asset_import.py --require-first-material` using
the model Python environment and `PYTHONPATH=src`. The test creates a unique
asset, compares its first and settled fixed-camera previews, and retains the
source/registered asset while deleting only its scene instance.

The color-count assertion is specific to the green test fixture against its
neutral road background, not a general material validator. View both images.
This patch does not establish texture-streaming residency, correct lighting,
cooked-build shader availability, or a bounded compile duration; a very slow
compile can still exceed the client RPC timeout and requires normal ownership
reconciliation. No fixed sleep is used as a production readiness signal.
