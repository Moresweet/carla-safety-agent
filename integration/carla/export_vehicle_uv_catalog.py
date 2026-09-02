"""Export every registered CARLA vehicle mesh and describe its material slots.

Run with UE4Editor-Cmd. The output manifest maps CARLA blueprint IDs to FBX
files and reports material names so bodywork slots can be selected reproducibly.
"""
import json
import os
import re
import unreal

OUTPUT = os.environ.get("CARLA_VEHICLE_EXPORT_DIR", "/tmp/carla-vehicle-meshes")
os.makedirs(OUTPUT, exist_ok=True)

factory_class = unreal.load_object(
    None, "/Game/Carla/Blueprints/Vehicles/VehicleFactory.VehicleFactory_C")
if not factory_class:
    raise RuntimeError("VehicleFactory generated class was not found")
factory = unreal.get_default_object(factory_class)
vehicles = factory.get_editor_property("vehicles")
manifest = {}
manifest_path = os.path.join(OUTPUT, "manifest.json")
if os.path.isfile(manifest_path):
    with open(manifest_path) as stream:
        manifest = json.load(stream)

for vehicle in vehicles:
    blueprint_id = "vehicle.{}.{}".format(vehicle.make, vehicle.model).lower()
    actor_class = vehicle.get_editor_property("class")
    actor = unreal.get_default_object(actor_class)
    component = actor.get_editor_property("mesh")
    mesh = component.get_editor_property("skeletal_mesh")
    if not mesh:
        unreal.log_warning("VEHICLE_UV_SKIP {} no skeletal mesh".format(blueprint_id))
        continue
    slots = []
    for index, entry in enumerate(mesh.get_editor_property("materials")):
        material = entry.get_editor_property("material_interface")
        slots.append({
            "index": index,
            "slot": str(entry.get_editor_property("material_slot_name")),
            "material": material.get_path_name() if material else "",
        })
    stem = re.sub(r"[^a-z0-9_-]", "-", blueprint_id)
    fbx = os.path.join(OUTPUT, stem + ".fbx")
    previously_attempted = blueprint_id in manifest
    task = unreal.AssetExportTask()
    task.set_editor_property("object", mesh)
    task.set_editor_property("filename", fbx)
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    task.set_editor_property("replace_identical", True)
    task.set_editor_property("write_empty_files", False)
    manifest[blueprint_id] = {
        "mesh": mesh.get_path_name(),
        "fbx": fbx,
        "slots": slots,
        "base_type": str(vehicle.base_type),
    }
    with open(manifest_path, "w") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
    if os.path.isfile(fbx) and os.path.getsize(fbx) > 0:
        unreal.log_warning("VEHICLE_UV_REUSED {} {}".format(blueprint_id, fbx))
        continue
    if previously_attempted:
        manifest[blueprint_id]["export_error"] = "UE4 FBX exporter failed"
        with open(manifest_path, "w") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
        unreal.log_error("VEHICLE_UV_SKIPPED_AFTER_CRASH " + blueprint_id)
        continue
    if not unreal.Exporter.run_asset_export_task(task):
        unreal.log_error("VEHICLE_UV_EXPORT_FAILED " + blueprint_id)
        continue
    unreal.log_warning("VEHICLE_UV_EXPORTED {} {}".format(blueprint_id, fbx))

with open(manifest_path, "w") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True)
unreal.log_warning("VEHICLE_UV_CATALOG_EXPORTED {} vehicles".format(len(manifest)))
