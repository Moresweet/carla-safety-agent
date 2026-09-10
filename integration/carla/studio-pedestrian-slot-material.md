# Versioned pedestrian clothing material

Apply `studio-pedestrian-slot-material.patch` after the studio material runtime
patch and existing pedestrian clothing material installation. It only changes
the exact-slot path for `BP_Walker_Female1_v1*`, `CharacterMesh0`, slot 14.
The base is the existing `M_CarlaPedestrianClothingRuntime` (roughness 0.82),
not vehicle paint. Other exact slots retain their previous base. Cached native
original-material restoration and tagged skeletal synchronization are unchanged.

Run `git apply --check` first, then rebuild `make CarlaUE4Editor` in
`Unreal/CarlaUE4`. Restart only through the idle-gated maintenance workflow,
with a saved scene and no active evaluation. Compiling alone does not update
the running simulator. This patch does not install the clothing material asset.

The local ten-action compile/link passed. Native texture version regression
`pedestrian-texture-versions-b985f3c394464f5798295aae1060759c` verified slot 14,
bridge restart, original-material undo, checkerboard redo/respawn (124 → 130),
an unrelated green-clothed walker and referenced texture bundle bytes.
Actual images were inspected. No claim of arbitrary walker layout support.
