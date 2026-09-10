# Asset import outcomes

All project import entry points now require an Unreal exit code of zero and a
matching asset ID, blueprint ID, and generated mesh path before registration.
A result file alone is insufficient. The old permissive shutdown-warning
registration is no longer available, including through the ordinary web page.
Unreadable or malformed registries fail closed instead of becoming an empty
registry and overwriting earlier entries. Existing entries are retained.

Each attempt writes `import-attempt-<id>.json` in its Blender job before starting
Unreal. The record contains the owner process identity, unique attempt ID,
request/result paths, and exact Unreal destination. Writes are atomic and
fsynced. Each commandlet uses a separate absolute engine log, not the live
server's default log. The same-project import lock rejects concurrent imports
instead of silently accumulating blocked HTTP requests.

States: `preparing`, `importing`, `registered`, `needs_attention`. An interrupted
process may leave `importing`; that is an uncertain outcome, not proof that the
child process is still running or that it is safe to retry. Do not register,
retry or delete assets from that state without inspecting the recorded attempt.
Failure preserves created assets and reports the destination; automatic asset
rollback is not implemented. Existing destination folders are never overwritten.

`GET /blender/imports` returns the newest 100 recorded attempts. Asset Workshop
shows both successful and failed attempts, including report paths. Old assets
have no invented attempt records. Refresh errors explicitly label stale data.

`tools/regression_asset_import.py` creates one uniquely named source/Unreal asset,
checks strict import and duplicate-name rejection, spawns a single instance for
first/settled screenshots, then removes that instance and restores the camera.
Source and Unreal assets remain registered for traceability. This is not a
rollback test and does not claim material readiness from import success alone.

The 2026-09-10 test `asset-import-1ffefb6325784dc6a0f93c34cf8494ba` demonstrated
that a successful import can still render a gray fallback on its first runtime
load, then the requested green material three seconds later. Runtime shader
readiness is being addressed separately in the native mesh factory; a fixed
sleep is not a readiness guarantee.
