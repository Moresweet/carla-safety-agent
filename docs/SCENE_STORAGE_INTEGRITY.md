# Scene history integrity

Scene heads and versions are bounded regular JSON files (16 MiB maximum).
Duplicate keys, non-finite special JSON values, linked scene folders/files/locks,
invalid history cursors and mismatched scene/version identities are rejected.
The selected current version must agree with its head's name, map and object
count. Saving cannot silently extend an invalid current version. Historical
branches remain readable by explicit version ID; branching does not delete files.
Histories are bounded to 10,000 entries; unsupported large histories are not trimmed.

Writes use unique exclusive temporary files, flush the file, replace the target,
then flush its parent directory. Newly created scene folder entries are flushed
to their parent. A failure before replacement preserves the previous target.
If directory flushing fails after replacement, the error explicitly says the
file was already replaced: inspect it before retrying. Failed temporary files
or an orphaned new version are retained for inspection, not silently deleted.

This is not a transaction across CARLA and the filesystem, a proof against
all power-loss/filesystem behavior, or protection against a malicious local
process racing directory renames. Do not infer a successful world restore from
a history-file update alone. Existing per-scene file locks and expected-version
checks remain in force; the bridge separately owns native scene operations.

Validation covers damaged heads/versions, symlinks, duplicate keys, oversized
files, Boolean history directions, flush failures and failed head publication.
Existing 92 readable local scene heads/current versions passed compatibility
checks before native regression. Native
`pedestrian-texture-versions-4270df4711a845b784dc1ba20fd2ff7e` verified save,
restart, undo/redo, respawn (273 → 279), unrelated control and bundled PNG bytes;
the respawned checkerboard image was inspected, all owned actors removed,
same episode/asynchronous/zero sensors. Later current-head metadata checks and
post-replacement error wording are additionally covered by unit tests.
