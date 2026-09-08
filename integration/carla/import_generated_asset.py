"""Import one Blender FBX as a cooked CARLA static mesh. Runs inside UE4.26."""
import json
import os
from pathlib import Path

import unreal


request_path = Path(os.environ["CSA_UNREAL_IMPORT_REQUEST"])
request = json.loads(request_path.read_text(encoding="utf-8"))
fbx_path = Path(request["fbx_path"])
asset_id = request["asset_id"]
destination = "/Game/Carla/Static/Generated/" + asset_id
mesh_name = "SM_" + asset_id

if not fbx_path.is_file():
    raise RuntimeError("FBX does not exist: " + str(fbx_path))

options = unreal.FbxImportUI()
options.set_editor_property("import_mesh", True)
options.set_editor_property("import_as_skeletal", False)
options.set_editor_property("import_materials", True)
options.set_editor_property("import_textures", True)
options.static_mesh_import_data.set_editor_property("combine_meshes", True)
options.static_mesh_import_data.set_editor_property("generate_lightmap_u_vs", True)
options.static_mesh_import_data.set_editor_property("auto_generate_collision", True)

task = unreal.AssetImportTask()
task.set_editor_property("filename", str(fbx_path))
task.set_editor_property("destination_path", destination)
task.set_editor_property("destination_name", mesh_name)
task.set_editor_property("automated", True)
task.set_editor_property("replace_existing", True)
task.set_editor_property("save", True)
task.set_editor_property("options", options)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

mesh_path = destination + "/" + mesh_name
mesh = unreal.load_asset(mesh_path)
if not mesh:
    imported = [path for path in task.get_editor_property("imported_object_paths")
                if unreal.load_asset(path).get_class().get_name() == "StaticMesh"]
    if not imported:
        raise RuntimeError("Unreal imported no StaticMesh from " + str(fbx_path))
    mesh = unreal.load_asset(imported[0])
    mesh_path = imported[0]

# Build and bind an Unreal-native material. FBX material references alone are
# not stable across unattended reimports, especially for external textures.
material_name = "M_" + asset_id
material_path = destination + "/" + material_name
material = unreal.load_asset(material_path)
if not material:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        material_name, destination, unreal.Material, unreal.MaterialFactoryNew())
unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
texture_path = request.get("texture_path")
if texture_path and Path(texture_path).is_file():
    texture_task = unreal.AssetImportTask()
    texture_task.set_editor_property("filename", texture_path)
    texture_task.set_editor_property("destination_path", destination)
    texture_task.set_editor_property("destination_name", "T_" + asset_id)
    texture_task.set_editor_property("automated", True)
    texture_task.set_editor_property("replace_existing", True)
    texture_task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([texture_task])
    texture = unreal.load_asset(destination + "/T_" + asset_id)
    expression = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSample, -200, 0)
    expression.set_editor_property("texture", texture)
    output_name = "RGB"
else:
    rgba = request.get("color", [0.15, 0.55, 0.85, 1.0])
    expression = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, -200, 0)
    expression.set_editor_property("constant", unreal.LinearColor(*rgba))
    output_name = ""
unreal.MaterialEditingLibrary.connect_material_property(
    expression, output_name, unreal.MaterialProperty.MP_BASE_COLOR)
roughness = unreal.MaterialEditingLibrary.create_material_expression(
    material, unreal.MaterialExpressionConstant, -200, 180)
roughness.set_editor_property("r", float(request.get("roughness", 0.45)))
unreal.MaterialEditingLibrary.connect_material_property(
    roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
unreal.MaterialEditingLibrary.recompile_material(material)
unreal.EditorAssetLibrary.save_loaded_asset(material, False)
mesh.set_material(0, material)

unreal.EditorAssetLibrary.save_loaded_asset(mesh, False)
result = {
    "ok": True,
    "asset_id": asset_id,
    "blueprint_id": "generated.prop." + asset_id.lower(),
    "mesh_path": mesh.get_path_name(),
    "material_path": material.get_path_name(),
    "destination": destination,
    "source_fbx": str(fbx_path),
    "default_scale": 100.0,
}
result_path = Path(request["result_path"])
result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
unreal.log_warning("CSA_GENERATED_ASSET_IMPORTED " + mesh.get_path_name())
