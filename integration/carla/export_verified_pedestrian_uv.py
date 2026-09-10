"""Read-only commandlet export of the currently supported walker's source mesh.

CSA_PEDESTRIAN_UV_OUTPUT must be a new/empty output directory. No assets/maps
are saved. Exporting the bind pose does not reproduce a running animation.
"""
import json
import os
import unreal

output = os.environ['CSA_PEDESTRIAN_UV_OUTPUT']
os.makedirs(output, exist_ok=True)
blueprint = '/Game/Carla/Blueprints/Walkers/BP_Walker_Female1_v1.BP_Walker_Female1_v1_C'
actor_class = unreal.load_object(None, blueprint)
if not actor_class:
    raise RuntimeError('Verified walker class not found')
actor = unreal.get_default_object(actor_class)
component = actor.get_editor_property('mesh')
mesh = component.get_editor_property('skeletal_mesh')
if not mesh:
    raise RuntimeError('Verified walker has no skeletal mesh')
slots = []
for index in range(component.get_num_materials()):
    material = component.get_material(index)
    names = component.get_material_slot_names()
    slots.append({'slot': index, 'name': str(names[index]) if index < len(names) else str(index),
                  'material': material.get_path_name() if material else None})
manifest = {'blueprint_id': 'walker.pedestrian.0001', 'blueprint_class': blueprint,
            'mesh': mesh.get_path_name(), 'component': component.get_name(),
            'slots': slots, 'pose': 'source bind pose, not live animation', 'status': 'exporting'}
filename = os.path.join(output, 'walker.fbx')
manifest_path = os.path.join(output, 'manifest.json')
if os.path.exists(filename) or os.path.exists(manifest_path):
    raise RuntimeError('Refusing to overwrite an earlier export')
with open(manifest_path, 'x') as stream:
    json.dump(manifest, stream, indent=2)
options = unreal.FbxExportOption()
options.set_editor_property('level_of_detail', False)
options.set_editor_property('collision', False)
task = unreal.AssetExportTask()
for name, value in {'object': mesh, 'filename': filename, 'automated': True,
                    'prompt': False, 'replace_identical': False,
                    'write_empty_files': False, 'options': options}.items():
    task.set_editor_property(name, value)
if not unreal.Exporter.run_asset_export_task(task):
    raise RuntimeError('Walker source FBX export failed')
manifest.update(status='fbx_exported', fbx=filename)
with open(manifest_path+'.tmp', 'x') as stream:
    json.dump(manifest, stream, indent=2)
os.replace(manifest_path+'.tmp', manifest_path)
unreal.log_warning('VERIFIED_PEDESTRIAN_UV_EXPORTED '+filename)
