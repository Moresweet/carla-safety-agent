# FBX importer shutdown lifetime

Target: local Unreal Engine 4.26, FBX SDK 2020.1.1, Linux.

The real import probe stopped at `__cxa_pure_virtual` after the commandlet
reported success. Its stack passed through
`FbxBindingOperator::FunctionRegistry::UnregisterFunctionCreator`,
`FbxManager::Destroy`, `FFbxImporter::CleanUp`, and finally the UnrealEd
shared library's `__cxa_finalize` static destruction. Loading an already saved
mesh in a separate commandlet did not reproduce the failure.

`fbx-importer-preexit.patch` registers the existing `DeleteInstance` operation
once, when the importer is first requested, with `FCoreDelegates::OnPreExit`.
This releases the importer while the FBX shared library is still alive instead
of relying on cross-library static destructor ordering. It does not skip engine
shutdown, suppress a signal, or treat a nonzero import exit as success.

Check/apply the patch from the Unreal checkout; it is not a CARLA source patch.
Rebuild `UE4Editor Linux Development -NoHotReload`. A module-only build on this
Linux checkout omitted the circular-dependency relink and produced an UnrealEd
library with an unresolved `FbxAMatrix` destructor at process startup; do not use
its compile result as evidence of a runnable editor. Then build the project
target `CarlaUE4Editor Linux Development <absolute-CarlaUE4.uproject>
-NoHotReload` so its plugin binaries and module manifests match the engine.
Do not manually change build IDs to bypass module compatibility checks. Existing
running processes keep their loaded code; validation must launch a new import
commandlet. Do not overwrite an existing asset during the probe.

Acceptance requires a new FBX import to exit zero, a valid freshly written
result, native generation at the expected dimensions, and actor cleanup.
A successful compile or Python unit tests alone do not prove this fix.
The debug probe intentionally does not update the generated-asset registry;
its separately named Unreal assets remain on disk for inspection.
