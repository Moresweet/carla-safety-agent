#!/usr/bin/env python3
"""Blender-side worker. Run only through Blender's bundled Python runtime."""
import json
import math
import sys
from pathlib import Path

import bpy


def arguments():
    marker = sys.argv.index("--")
    return Path(sys.argv[marker + 1]), Path(sys.argv[marker + 2])


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_asset(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".fbx":
        bpy.ops.wm.fbx_import(filepath=str(path))
    elif suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path))
    else:
        raise ValueError(f"unsupported source format: {suffix}")


def create_primitive(spec):
    shape = spec.get("shape", "cube")
    operators = {
        "cube": lambda: bpy.ops.mesh.primitive_cube_add(),
        "cylinder": lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=48),
        "cone": lambda: bpy.ops.mesh.primitive_cone_add(vertices=48),
        "sphere": lambda: bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24),
        "plane": lambda: bpy.ops.mesh.primitive_plane_add(size=2),
    }
    if shape not in operators:
        raise ValueError(f"unsupported primitive: {shape}")
    operators[shape]()
    obj = bpy.context.object
    obj.name = str(spec.get("name", "GeneratedAsset"))[:63]
    dimensions = spec.get("dimensions", [2.0, 2.0, 2.0])
    obj.dimensions = tuple(max(0.01, float(value)) for value in dimensions)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def ensure_uv(obj):
    if obj.data.uv_layers:
        return
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def apply_material(spec, texture_path):
    rgba = spec.get("color", [0.15, 0.55, 0.85, 1.0])
    material = bpy.data.materials.new(name="CSA_Material")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = tuple(float(v) for v in rgba)
    principled.inputs["Roughness"].default_value = float(spec.get("roughness", 0.45))
    if texture_path:
        image = bpy.data.images.load(str(texture_path), check_existing=True)
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        material.node_tree.links.new(node.outputs["Color"], principled.inputs["Base Color"])
        material.node_tree.links.new(node.outputs["Alpha"], principled.inputs["Alpha"])
    for obj in mesh_objects():
        ensure_uv(obj)
        obj.data.materials.clear()
        obj.data.materials.append(material)


def export(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    blend = output / "asset.blend"
    glb = output / "asset.glb"
    fbx = output / "asset.fbx"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", export_apply=True)
    try:
        bpy.ops.export_scene.fbx(filepath=str(fbx), global_scale=100.0,
                                 apply_scale_options="FBX_SCALE_ALL",
                                 use_mesh_modifiers=True, mesh_smooth_type="FACE",
                                 use_tspace=True, axis_forward="-Z", axis_up="Y")
    except Exception as exc:
        print(f"CSA_FBX_WARNING={exc}")
        fbx = None
    return blend, glb, fbx


def main():
    spec_path, output = arguments()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    clear_scene()
    source = spec.get("source_path")
    if source:
        import_asset(Path(source))
    else:
        create_primitive(spec)
    apply_material(spec, Path(spec["texture_path"]) if spec.get("texture_path") else None)
    blend, glb, fbx = export(output)
    meshes = mesh_objects()
    manifest = {
        "ok": True,
        "name": spec.get("name", "GeneratedAsset"),
        "operation": "retexture" if source else "create",
        "objects": len(meshes),
        "vertices": sum(len(obj.data.vertices) for obj in meshes),
        "materials": sum(len(obj.data.materials) for obj in meshes),
        "outputs": {"blend": str(blend), "glb": str(glb),
                    "fbx": str(fbx) if fbx else None},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("CSA_RESULT=" + json.dumps(manifest))


if __name__ == "__main__":
    main()
