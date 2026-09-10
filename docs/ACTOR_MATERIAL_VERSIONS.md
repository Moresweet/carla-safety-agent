# Actor texture versions

The currently verified layout is a studio-created `vehicle.audi.a2`, component
`VehicleMesh`, material slot 4, at 2048×2048. Other vehicles, walkers, existing
unmanaged actors and legacy edits are not covered by this version contract.

Successful `/apply` responses for this layout carry `versionable: true` and a
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

Real browser export/upload/isolated import/confirmed native restore also passed:
`browser-bundle-restore-2adf01538ab94192aac950c7f95eef00`, actor 631 → 632,
matching texture digest, close-up checkerboard image inspected, stale and reused
approvals rejected and owned vehicle removed. The earlier
`browser-bundle-restore-f59a7fdbee39482e855151b0892a3fc8` passed data checks but
its distant image was insufficient for visual acceptance; it is not counted as
visual proof. Neither run establishes cross-machine execution.
