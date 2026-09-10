# Actor texture versions

Verified studio-created layouts are `vehicle.audi.a2` / `VehicleMesh` / slot 4
at 2048×2048 and `walker.pedestrian.0001` / `CharacterMesh0` / pants slot 14 at
1024×1024. Other models, unmanaged actors and legacy edits are not covered.
The walker requires the additional [native clothing-slot patch](../integration/carla/studio-pedestrian-slot-material.md),
which preserves the existing clothing shader instead of using vehicle paint.

Successful `/apply` or `/apply/pedestrian` responses for these layouts carry `versionable: true` and a
content-addressed PNG digest. Save a scene after editing to create a version;
this is scene-level undo/redo, not automatic per-stroke history.

Scene `actor_materials` entries reference stable object IDs, blueprint,
component, slot and texture digest. They never reference transient actor IDs.
Restore checks the verified layout and all referenced PNG checksums before
world mutation. It can respawn a missing selected actor and apply its texture
after resolving its exact runtime component. Unrelated user actors retain their
overrides. An explicit empty list clears tracked overrides on selected objects;
legacy documents with no field leave actor overrides unchanged.

Project bundles include referenced texture bytes and report required actor
slots. This does not package or validate the native vehicle asset, engine patch
or Python environment. Restore reviews disclose the selected-object scope and
are invalidated by changes to the captured actor texture state.

Application errors attempt compensating native and provenance updates. This is
not an atomic engine/disk transaction: a process crash or repeated persistence
failure can still require recovery. The first tracked edit caches the current
native material, which may already contain a legacy edit. Historical appearance
is not backfilled, and arbitrary vehicle factory-color attributes are not yet
part of this portability contract.

## Local evidence

- `vehicle-texture-versions-9eb2067c6a654863b790ccfa4d1fd395`: bridge restart,
  scene undo/redo, deletion and stable-ID respawn (612 → 618), referenced PNG
  bundle equality and an unrelated green vehicle retained. Reviewed images show
  red after undo, checkerboard after respawn and green on the control.
- `vehicle-uv-ad3bc6a747434f57afcb4472388c5c52`: real browser editing after
  bridge restart; target checkerboard image inspected. Both owned actors removed,
  same episode, asynchronous mode and zero residual sensors.
- 664 Python tests and TypeScript checking passed, including invalid layouts,
  corrupt PNG checksum rejection before mutation, controlled metadata-write
  failure compensation, empty-list clearing, legacy absence and stale reviews.

These finite tests are not a guarantee against all future simulator crashes.

- `pedestrian-texture-versions-b985f3c394464f5798295aae1060759c`: scene
  `a72c9d75ab504139bbb1c69829f3ee89`, stable ID `13e0c6be7f91447d8b40054e1f1d35f9`.
  Bridge restart, undo/redo, respawn (124 → 130), exact referenced bundle PNG
  and unrelated green pants preserved. Inspected original-pants undo,
  checkerboard respawn and green control images. Same episode, async, zero sensors.
- `pedestrian-uv-36bc3731783e41adb8f323f4aa73ff4a`: real browser source-UV
  editing after restart, browser `3bd4bd7c-231b-4dd9-b0ed-d950c819cbca`.
  Pants-only checkerboard image inspected; both owned walkers cleaned up.
- Shared PNG digests now cache native textures by digest **and resolution**,
  so a mixed Audi/walker restore does not reuse the first model's resolution.
- `browser-bundle-restore-fc39e8fd51e547c7b4ea610eb623e34f`: browser
  `9a0eeeee-3bac-4a14-aed9-ac99b59a7d1b`, separate export/upload/isolated import/
  confirmed world restore of pants texture, actor 140 → 141. Matching digest,
  inspected checkerboard image, stale/reused consent rejected, owned actor removed.

Real browser export/upload/isolated import/confirmed native restore also passed:
`browser-bundle-restore-2adf01538ab94192aac950c7f95eef00`, actor 631 → 632,
matching texture digest, close-up checkerboard image inspected, stale and reused
approvals rejected and owned vehicle removed. The earlier
`browser-bundle-restore-f59a7fdbee39482e855151b0892a3fc8` passed data checks but
its distant image was insufficient for visual acceptance; it is not counted as
visual proof. Neither run establishes cross-machine execution.
