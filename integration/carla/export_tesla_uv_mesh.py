"""Export the CARLA Tesla skeletal mesh for UV tooling.

Run with UE4Editor-Cmd's Python commandlet. Set CARLA_TESLA_EXPORT to override
the output FBX path.
"""

import os

import unreal


asset = unreal.load_asset(
    '/Game/Carla/Static/Car/4Wheeled/Tesla/SM_TeslaM3_v2')
if not asset:
    raise RuntimeError('Tesla Model 3 skeletal mesh was not found')

output = os.environ.get('CARLA_TESLA_EXPORT', '/tmp/carla-tesla-model3.fbx')
task = unreal.AssetExportTask()
task.set_editor_property('object', asset)
task.set_editor_property('filename', output)
task.set_editor_property('automated', True)
task.set_editor_property('prompt', False)
task.set_editor_property('replace_identical', True)
task.set_editor_property('write_empty_files', False)

if not unreal.Exporter.run_asset_export_task(task):
    raise RuntimeError('Unreal failed to export the Tesla mesh')

unreal.log_warning('TESLA_UV_MESH_EXPORTED ' + output)
