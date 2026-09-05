"""Export static counterparts for vehicle skeletal meshes that crash UE4 FBX export."""
import json
import os
import unreal


OUTPUT = os.environ.get("CARLA_VEHICLE_EXPORT_DIR", "/tmp/carla-vehicle-meshes")
ASSETS = {
    "vehicle.mercedes.coupe_2020":
        "/Game/Carla/Static/Car/4Wheeled/ParkedVehicles/MercedesCCC/SM_MercedesCCC_Parked",
    "vehicle.mini.cooper_s_2021":
        "/Game/Carla/Static/Car/4Wheeled/ParkedVehicles/Mini2021/SM_Mini2021_parked",
}
os.makedirs(OUTPUT, exist_ok=True)
result = {}

for blueprint_id, path in ASSETS.items():
    mesh = unreal.load_asset(path)
    if not mesh:
        raise RuntimeError("Static preview mesh was not found: " + path)
    slots = []
    for index, material in enumerate(mesh.get_editor_property("static_materials")):
        slots.append({"index": index,
                      "slot": str(material.get_editor_property("material_slot_name"))})
    filename = os.path.join(OUTPUT, blueprint_id.replace(".", "-") + "-preview.fbx")
    task = unreal.AssetExportTask()
    task.set_editor_property("object", mesh)
    task.set_editor_property("filename", filename)
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    task.set_editor_property("replace_identical", True)
    task.set_editor_property("write_empty_files", False)
    if not unreal.Exporter.run_asset_export_task(task):
        raise RuntimeError("Static preview export failed: " + blueprint_id)
    result[blueprint_id] = {"fbx": filename, "slots": slots}

with open(os.path.join(OUTPUT, "missing-preview-manifest.json"), "w") as stream:
    json.dump(result, stream, indent=2, sort_keys=True)
unreal.log_warning("MISSING_VEHICLE_PREVIEWS_EXPORTED " + str(len(result)))
