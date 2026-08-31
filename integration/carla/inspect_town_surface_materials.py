"""Print material assignments for representative Town04 road/building actors."""
import unreal

unreal.EditorLevelLibrary.load_level("/Game/Carla/Maps/Town04")
counts = {"road": 0, "building": 0}
seen = set()
for actor in unreal.EditorLevelLibrary.get_all_level_actors():
    label = actor.get_actor_label()
    kind = "road" if label.startswith("Road_Road_") else (
        "building" if label.startswith(("BP_House", "SM_House", "SM_TerracedHouse")) else None)
    if not kind or counts[kind] >= 12:
        continue
    for component in actor.get_components_by_class(unreal.MeshComponent):
        materials = []
        for index in range(component.get_num_materials()):
            material = component.get_material(index)
            materials.append(material.get_path_name() if material else "None")
        signature = (kind, tuple(materials))
        if signature in seen:
            continue
        seen.add(signature)
        counts[kind] += 1
        unreal.log_warning("SURFACE_MATERIAL {} {} {} {}".format(
            kind, label, actor.get_actor_location(), " | ".join(materials)))
