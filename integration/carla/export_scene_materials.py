"""Read-only UE commandlet: export real components and UV0 material slots.

CSA_MATERIAL_EXPORT_REQUEST points to {map, targets, output}. Never saves maps.
Spline-deformed and instanced geometry is explicitly unsupported for web preview.
"""
import hashlib
import json
import os
import unreal

with open(os.environ['CSA_MATERIAL_EXPORT_REQUEST']) as stream:
    request = json.load(stream)
output = request['output']
os.makedirs(output, exist_ok=True)
if not unreal.EditorLevelLibrary.load_level(request['map']):
    raise RuntimeError('Unable to load requested map for read-only export')
targets = set(request['targets'])
catalog = {'schema_version': 'carla-material-catalog/1', 'map': request['map'], 'actors': {}}

def persist():
    with open(os.path.join(output, 'catalog.json.tmp'), 'w') as stream:
        json.dump(catalog, stream, indent=2)
    os.replace(os.path.join(output, 'catalog.json.tmp'), os.path.join(output, 'catalog.json'))

for actor in unreal.EditorLevelLibrary.get_all_level_actors():
    name = actor.get_name()
    if name not in targets:
        continue
    entries = []
    catalog['actors'][name] = entries
    for component in actor.get_components_by_class(unreal.MeshComponent):
        if 'Tagged' in component.get_class().get_name():
            continue
        entry = {'component': component.get_name(), 'class': component.get_class().get_name(),
                 'slots': [], 'status': 'unsupported_geometry'}
        entries.append(entry)
        if isinstance(component, (unreal.SplineMeshComponent, unreal.InstancedStaticMeshComponent)):
            entry['reason'] = 'Deformed/instanced geometry requires baking, not raw mesh export'
            continue
        if isinstance(component, unreal.SkeletalMeshComponent):
            mesh = component.get_editor_property('skeletal_mesh')
        elif isinstance(component, unreal.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
        else:
            continue
        if not mesh: continue
        key = hashlib.sha256(mesh.get_path_name().encode()).hexdigest()[:20]
        entry.update(mesh=mesh.get_path_name(), mesh_key=key, status='exporting')
        slot_names = component.get_material_slot_names()
        for index in range(component.get_num_materials()):
            material = component.get_material(index)
            entry['slots'].append({'slot':index, 'name':str(slot_names[index]) if index<len(slot_names) else str(index),
                                   'original_material':material.get_path_name() if material else None})
        persist()
        fbx = os.path.join(output, key+'.fbx')
        options = unreal.FbxExportOption()
        options.set_editor_property('level_of_detail', False)
        options.set_editor_property('collision', False)
        task = unreal.AssetExportTask()
        for property_name, value in {'object':mesh,'filename':fbx,'automated':True,'prompt':False,
                                     'replace_identical':True,'write_empty_files':False,'options':options}.items():
            task.set_editor_property(property_name,value)
        exported = os.path.isfile(fbx) or unreal.Exporter.run_asset_export_task(task)
        entry.update(status='fbx_exported' if exported else 'export_failed', fbx=fbx)
        persist()
    unreal.log_warning('STUDIO_MATERIAL_EXPORTED '+name)
catalog['missing_targets'] = sorted(targets-set(catalog['actors']))
persist()
