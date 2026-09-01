"""Export the European HGV skeletal mesh and report its material slots."""
import os
import unreal

ASSET = "/Game/Carla/Static/Truck/European_HGV/SK_European_HGV"
mesh = unreal.load_asset(ASSET)
if not mesh:
    raise RuntimeError("European HGV skeletal mesh was not found")

for index, material in enumerate(mesh.get_editor_property("materials")):
    interface = material.get_editor_property("material_interface")
    unreal.log_warning("HGV_MATERIAL_SLOT {} {} {}".format(
        index, material.get_editor_property("material_slot_name"),
        interface.get_path_name() if interface else "None"))

output = os.environ.get("CARLA_HGV_EXPORT", "/tmp/carla-european-hgv.fbx")
task = unreal.AssetExportTask()
task.set_editor_property("object", mesh)
task.set_editor_property("filename", output)
task.set_editor_property("automated", True)
task.set_editor_property("prompt", False)
task.set_editor_property("replace_identical", True)
task.set_editor_property("write_empty_files", False)
if not unreal.Exporter.run_asset_export_task(task):
    raise RuntimeError("Unreal failed to export the European HGV mesh")
unreal.log_warning("HGV_UV_MESH_EXPORTED " + output)
