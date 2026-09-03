#!/usr/bin/env python3
"""Local HTTP bridge for applying browser-composed liveries to CARLA."""

import io
import json
import os
import math
import threading
import time
import hashlib
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import carla
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from carla_safety_agent.carla_adapter import CarlaAdapter
from carla_safety_agent.natural_language import NaturalLanguageCompiler


HOST = "127.0.0.1"
PORT = int(os.environ.get("BRIDGE_PORT", "8765"))
CARLA_PORT = int(os.environ.get("CARLA_PORT", "2000"))
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
HIGHLIGHT_COLORS = {
    "vehicle": carla.Color(0, 170, 255),
    "walker": carla.Color(255, 200, 0),
    "building": carla.Color(190, 80, 255),
    "road": carla.Color(255, 70, 70),
    "prop": carla.Color(60, 220, 120),
}
_hero_lock = threading.Event()
_map_cache = {}
_environment_cache = {}
_actor_object_names = {}
_user_created_actor_ids = set()
_thumbnail_cache = {}
_thumbnail_lock = threading.Lock()
_thumbnail_dir = os.environ.get("THUMBNAIL_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), ".runtime", "thumbnails"))
ENVIRONMENT_CATEGORIES = {
    "buildings": (carla.CityObjectLabel.Buildings, "architecture", "building"),
    "bridges": (carla.CityObjectLabel.Bridge, "architecture", "building"),
    "walls": (carla.CityObjectLabel.Walls, "architecture", "building"),
    "fences": (carla.CityObjectLabel.Fences, "architecture", "building"),
    "roads": (carla.CityObjectLabel.Roads, "transport", "road"),
    "road_lines": (carla.CityObjectLabel.RoadLines, "transport", "road"),
    "sidewalks": (carla.CityObjectLabel.Sidewalks, "transport", "road"),
    "ground": (carla.CityObjectLabel.Ground, "terrain", "road"),
    "terrain": (carla.CityObjectLabel.Terrain, "terrain", "road"),
    "vegetation": (carla.CityObjectLabel.Vegetation, "nature", "building"),
    "water": (carla.CityObjectLabel.Water, "nature", "road"),
    "poles": (carla.CityObjectLabel.Poles, "street_furniture", "building"),
    "guard_rails": (carla.CityObjectLabel.GuardRail, "street_furniture", "building"),
    "traffic_signs": (carla.CityObjectLabel.TrafficSigns, "traffic_control", "building"),
    "traffic_lights": (carla.CityObjectLabel.TrafficLight, "traffic_control", "building"),
    "parked_cars": (carla.CityObjectLabel.Car, "vehicles", "vehicle"),
    "dynamic_props": (carla.CityObjectLabel.Dynamic, "props", "building"),
    "static_props": (carla.CityObjectLabel.Static, "props", "building"),
}


def compile_scenario(data: dict, execute: bool = False) -> dict:
    compilation = NaturalLanguageCompiler().compile(
        str(data.get("description", "")), int(data.get("seed", 7)))
    response = {"ok": True, "scenario": compilation.scenario.to_dict(),
                "warnings": list(compilation.warnings),
                "extracted": compilation.extracted}
    if execute:
        output = PROJECT_ROOT / ".runtime" / "generated-scenarios"
        result = CarlaAdapter(HOST, CARLA_PORT, 120.0).run(
            compilation.scenario, output, render=True)
        response["result"] = result.to_dict()
        response["output_dir"] = str(output)
    return response


def decode_texture(payload: bytes, size: tuple[int, int]) -> tuple[Image.Image, carla.TextureColor]:
    image = Image.open(io.BytesIO(payload)).convert("RGBA")
    if image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    texture = carla.TextureColor(image.width, image.height)
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            texture.set(x, y, carla.Color(r, g, b, a))
    return image, texture


def connect_world():
    client = carla.Client(HOST, CARLA_PORT)
    client.set_timeout(20.0)
    return client.get_world()


def vector(location) -> dict:
    return {"x": round(location.x, 3), "y": round(location.y, 3),
            "z": round(location.z, 3)}


def look_at(source, target) -> carla.Rotation:
    dx, dy, dz = target.x-source.x, target.y-source.y, target.z-source.z
    return carla.Rotation(
        pitch=math.degrees(math.atan2(dz, math.hypot(dx, dy))),
        yaw=math.degrees(math.atan2(dy, dx)))


def hero_actor(world):
    heroes = [actor for actor in world.get_actors().filter("vehicle.*")
              if actor.attributes.get("role_name") == "hero"]
    return heroes[0] if heroes else None


def focus_location(world, location, distance=12.0, height=6.0):
    _hero_lock.clear()
    camera = location + carla.Location(x=-distance, y=-distance, z=height)
    world.get_spectator().set_transform(
        carla.Transform(camera, look_at(camera, location)))


def actor_record(actor) -> dict:
    kind = ("walker" if actor.type_id.startswith("walker.") else
            "prop" if actor.type_id.startswith("static.prop.") else "vehicle")
    extent = actor.bounding_box.extent
    return {"key": f"actor:{actor.id}", "id": actor.id, "kind": kind,
            "name": actor.type_id, "label": f"{actor.type_id} · #{actor.id}",
            "location": vector(actor.get_location()),
            "extent": vector(extent),
            "hero": actor.attributes.get("role_name") == "hero",
            "origin": "user" if actor.id in _user_created_actor_ids else "native",
            "user_created": actor.id in _user_created_actor_ids}


def environment_objects(world, category: str):
    if category not in ENVIRONMENT_CATEGORIES:
        raise RuntimeError(f"Unknown environment category: {category}")
    map_name = world.get_map().name
    key = (map_name, category)
    if key not in _environment_cache:
        label = ENVIRONMENT_CATEGORIES[category][0]
        _environment_cache[key] = list(world.get_environment_objects(label))
    return _environment_cache[key]


def environment_record(obj, category: str) -> dict:
    _, group, coarse = ENVIRONMENT_CATEGORIES[category]
    box = obj.bounding_box
    location = box.location
    return {"key": f"environment:{obj.id}", "id": str(obj.id),
            "source": "environment", "origin": "native", "user_created": False,
            "category": category, "group": group,
            "kind": coarse, "name": obj.name,
            "label": f"{obj.name} · {str(obj.id)[-6:]}",
            "location": vector(location), "extent": vector(box.extent),
            "rotation": {"pitch": obj.transform.rotation.pitch,
                         "yaw": obj.transform.rotation.yaw,
                         "roll": obj.transform.rotation.roll}}


def catalog_categories() -> dict:
    world = connect_world()
    dynamic = world.get_actors()
    categories = []
    for name, (_, group, coarse) in ENVIRONMENT_CATEGORIES.items():
        categories.append({"id": name, "group": group, "coarse": coarse,
                           "count": len(environment_objects(world, name)),
                           "editable": "visibility_texture"})
    categories.extend([
        {"id": "vehicles", "group": "dynamic", "coarse": "vehicle",
         "count": len(dynamic.filter("vehicle.*")), "editable": "full"},
        {"id": "pedestrians", "group": "dynamic", "coarse": "walker",
         "count": len(dynamic.filter("walker.*")), "editable": "full"},
        {"id": "spawned_props", "group": "dynamic", "coarse": "building",
         "count": len(dynamic.filter("static.prop.*")), "editable": "full"},
    ])
    return {"ok": True, "map": world.get_map().name, "categories": categories}


def catalog_objects(category: str, query: str, offset: int, limit: int) -> dict:
    world = connect_world()
    if category in ENVIRONMENT_CATEGORIES:
        records = [environment_record(obj, category)
                   for obj in environment_objects(world, category)]
    else:
        pattern = {"vehicles": "vehicle.*", "pedestrians": "walker.*",
                   "spawned_props": "static.prop.*"}.get(category)
        if not pattern:
            raise RuntimeError(f"Unknown category: {category}")
        records = [actor_record(actor) | {"source": "actor", "category": category,
                                             "group": "dynamic"}
                   for actor in world.get_actors().filter(pattern)]
    if query:
        needle = query.casefold()
        records = [item for item in records
                   if needle in item["name"].casefold() or needle in str(item["id"])]
    total = len(records)
    return {"ok": True, "category": category, "total": total,
            "offset": offset, "limit": limit,
            "objects": records[offset:offset+limit]}


def find_environment(world, object_id: int):
    for category in ENVIRONMENT_CATEGORIES:
        for obj in environment_objects(world, category):
            if int(obj.id) == object_id:
                return category, obj
    raise RuntimeError(f"Environment object {object_id} was not found")


def focus_environment(object_id: int) -> dict:
    world = connect_world()
    category, obj = find_environment(world, object_id)
    record = environment_record(obj, category)
    loc, ext = record["location"], record["extent"]
    center = carla.Location(x=loc["x"], y=loc["y"], z=loc["z"])
    extent = carla.Vector3D(x=ext["x"], y=ext["y"], z=ext["z"])
    color = HIGHLIGHT_COLORS[record["kind"]]
    world.debug.draw_box(carla.BoundingBox(center, extent), obj.transform.rotation,
                         thickness=0.15, color=color, life_time=8.0)
    focus_location(world, center, max(10.0, extent.x*2), max(6.0, extent.z*2))
    return {"ok": True, "object": record}


def set_environment_visibility(object_id: int, enabled: bool) -> dict:
    world = connect_world()
    category, obj = find_environment(world, object_id)
    world.enable_environment_objects({obj.id}, enabled)
    return {"ok": True, "id": str(obj.id), "category": category,
            "visible": enabled}


def spawn_object(blueprint_id: str, transform_data: dict) -> dict:
    world = connect_world()
    blueprint = world.get_blueprint_library().find(blueprint_id)
    if not blueprint_id.startswith(("vehicle.", "walker.", "static.prop.")):
        raise RuntimeError("Only vehicle, walker, and static.prop blueprints are spawnable")
    location = transform_data.get("location", {})
    rotation = transform_data.get("rotation", {})
    spawn_location = carla.Location(x=float(location.get("x", 0)),
                                    y=float(location.get("y", 0)),
                                    z=float(location.get("z", 1)))
    if transform_data.get("snap_to_ground"):
        waypoint = world.get_map().get_waypoint(
            spawn_location, project_to_road=True,
            lane_type=carla.LaneType.Driving | carla.LaneType.Sidewalk)
        if waypoint:
            spawn_location.z = waypoint.transform.location.z + (
                0.5 if blueprint_id.startswith("vehicle.") else
                1.0 if blueprint_id.startswith("walker.") else 0.5)
    transform = carla.Transform(
        spawn_location,
        carla.Rotation(pitch=float(rotation.get("pitch", 0)),
                       yaw=float(rotation.get("yaw", 0)),
                       roll=float(rotation.get("roll", 0))))
    if (blueprint_id.startswith("vehicle.") and blueprint.has_attribute("role_name")
            and not hero_actor(world)):
        blueprint.set_attribute("role_name", "hero")
    before = set(world.get_names_of_all_objects())
    actor = world.spawn_actor(blueprint, transform)
    _user_created_actor_ids.add(actor.id)
    if blueprint_id.startswith("vehicle."):
        actor.set_autopilot(False)
        actor.set_target_velocity(carla.Vector3D())
        actor.set_target_angular_velocity(carla.Vector3D())
        actor.apply_control(carla.VehicleControl(brake=1.0, hand_brake=True))
        actor.set_simulate_physics(False)
    after = set(world.get_names_of_all_objects())
    created_names = sorted(after-before)
    if created_names:
        _actor_object_names[actor.id] = created_names[-1]
    return {"ok": True, "object": actor_record(actor)}


def update_actor(actor_id: int, transform_data: dict) -> dict:
    world = connect_world()
    actor = world.get_actor(actor_id)
    if not actor:
        raise RuntimeError(f"Actor {actor_id} is not running")
    current = actor.get_transform()
    loc, rot = transform_data.get("location", {}), transform_data.get("rotation", {})
    actor.set_transform(carla.Transform(
        carla.Location(x=float(loc.get("x", current.location.x)),
                       y=float(loc.get("y", current.location.y)),
                       z=float(loc.get("z", current.location.z))),
        carla.Rotation(pitch=float(rot.get("pitch", current.rotation.pitch)),
                       yaw=float(rot.get("yaw", current.rotation.yaw)),
                       roll=float(rot.get("roll", current.rotation.roll)))))
    return {"ok": True, "object": actor_record(actor)}


def duplicate_actor(actor_id: int) -> dict:
    world = connect_world()
    actor = world.get_actor(actor_id)
    if not actor:
        raise RuntimeError(f"Actor {actor_id} is not running")
    transform = actor.get_transform()
    transform.location += carla.Location(x=3.0, y=3.0, z=0.5)
    return spawn_object(actor.type_id, {"location": vector(transform.location),
                                        "rotation": {"pitch": transform.rotation.pitch,
                                                     "yaw": transform.rotation.yaw,
                                                     "roll": transform.rotation.roll}})


def delete_actor(actor_id: int) -> dict:
    world = connect_world()
    actor = world.get_actor(actor_id)
    if not actor:
        raise RuntimeError(f"Actor {actor_id} is not running")
    type_id = actor.type_id
    actor.destroy()
    _actor_object_names.pop(actor_id, None)
    _user_created_actor_ids.discard(actor_id)
    return {"ok": True, "actor_id": actor_id, "type_id": type_id}


def spawnable_blueprints(query: str, limit: int) -> dict:
    world = connect_world()
    patterns = ("vehicle.*", "walker.pedestrian.*", "static.prop.*")
    ids = sorted({bp.id for pattern in patterns
                  for bp in world.get_blueprint_library().filter(pattern)})
    if query:
        ids = [item for item in ids if query.casefold() in item.casefold()]
    return {"ok": True, "total": len(ids), "blueprints": ids[:limit]}


def blueprint_thumbnail(blueprint_id: str) -> bytes:
    if blueprint_id in _thumbnail_cache:
        return _thumbnail_cache[blueprint_id]
    if not blueprint_id.startswith(("vehicle.", "walker.", "static.prop.")):
        raise RuntimeError("Unsupported thumbnail blueprint")
    with _thumbnail_lock:
        if blueprint_id in _thumbnail_cache:
            return _thumbnail_cache[blueprint_id]
        os.makedirs(_thumbnail_dir, exist_ok=True)
        cache_path = os.path.join(_thumbnail_dir, hashlib.sha256(blueprint_id.encode()).hexdigest() + ".png")
        if os.path.isfile(cache_path):
            with open(cache_path, "rb") as cached:
                payload = cached.read()
            _thumbnail_cache[blueprint_id] = payload
            return payload
        world = connect_world()
        library = world.get_blueprint_library()
        actor = sensor = None
        try:
            actor = world.try_spawn_actor(
                library.find(blueprint_id),
                carla.Transform(carla.Location(x=0, y=0, z=800), carla.Rotation(yaw=25)))
            if not actor:
                raise RuntimeError(f"Could not stage {blueprint_id} for preview")
            try:
                actor.set_simulate_physics(False)
            except RuntimeError:
                pass
            extent = actor.bounding_box.extent
            radius = max(1.2, extent.x, extent.y, extent.z)
            center = carla.Location(actor.bounding_box.location.x,
                                    actor.bounding_box.location.y,
                                    actor.bounding_box.location.z)
            actor.get_transform().transform(center)
            camera_bp = library.find("sensor.camera.rgb")
            camera_bp.set_attribute("image_size_x", "480")
            camera_bp.set_attribute("image_size_y", "270")
            camera_bp.set_attribute("fov", "48")
            camera = center + carla.Location(x=-radius*3.0, y=-radius*3.0,
                                              z=max(radius*1.4, extent.z*0.9))
            sensor = world.spawn_actor(
                camera_bp, carla.Transform(camera, look_at(camera, center)))
            captured = threading.Event()
            frames = []
            def receive(frame):
                if frames:
                    return
                rgba = Image.frombuffer("RGBA", (frame.width, frame.height),
                                        bytes(frame.raw_data), "raw", "BGRA")
                stream = io.BytesIO()
                rgba.convert("RGB").save(stream, "PNG", optimize=True)
                frames.append(stream.getvalue())
                captured.set()
            sensor.listen(receive)
            if not captured.wait(8.0):
                raise RuntimeError(f"Timed out rendering {blueprint_id}")
            _thumbnail_cache[blueprint_id] = frames[0]
            temporary = cache_path + ".tmp"
            with open(temporary, "wb") as cached:
                cached.write(frames[0])
            os.replace(temporary, cache_path)
            return frames[0]
        finally:
            if sensor:
                sensor.stop()
                sensor.destroy()
            if actor:
                actor.destroy()


def runtime_name_for_actor(world, actor):
    mapped = _actor_object_names.get(actor.id)
    names = set(world.get_names_of_all_objects())
    if mapped in names:
        return mapped
    if actor.type_id == "vehicle.tesla.model3":
        matches = sorted(name for name in names if name.startswith("BP_TeslaM3_C_"))
        if matches:
            return matches[-1]
    if actor.type_id == "vehicle.carlamotors.european_hgv":
        matches = sorted(name for name in names if name.startswith("BP_European_HGV_C_"))
        if matches:
            return matches[-1]
    if actor.type_id == "walker.pedestrian.0001":
        matches = sorted(name for name in names if name.startswith("BP_Walker_Female1_v1_C_"))
        if matches:
            return matches[-1]
    raise RuntimeError(
        f"Runtime mesh identity is unavailable for actor {actor.id} ({actor.type_id}); "
        "respawn it from Create Objects to register the mapping")


def scene_state() -> dict:
    world = connect_world()
    _user_created_actor_ids.intersection_update(
        actor.id for actor in world.get_actors())
    actors = [actor_record(actor) for actor in world.get_actors()
              if actor.type_id.startswith(("vehicle.", "walker."))]
    map_name = world.get_map().name
    cached = _map_cache.get(map_name)
    if not cached:
        points = [waypoint.transform.location
                  for waypoint in world.get_map().generate_waypoints(12.0)]
        bounds = ({"min_x": min(p.x for p in points), "max_x": max(p.x for p in points),
                   "min_y": min(p.y for p in points), "max_y": max(p.y for p in points)}
                  if points else {"min_x": 0, "max_x": 1, "min_y": 0, "max_y": 1})
        cached = {"bounds": bounds, "road_points": [vector(p) for p in points]}
        _map_cache.clear()
        _map_cache[map_name] = cached
    bounds = cached["bounds"]
    spectator = world.get_spectator().get_transform()
    hero = hero_actor(world)
    static_targets = [
        {"key": "static:building:BP_House16", "kind": "building",
         "name": "BP_House16", "label": "BP_House16 · verified walls",
         "location": {"x": 77.151, "y": -191.293, "z": 4.0},
         "extent": {"x": 8.0, "y": 8.0, "z": 5.0}},
        {"key": "static:road:Town04", "kind": "road",
         "name": "Town04 roads", "label": "Town04 · road surfaces",
         "location": {"x": (bounds["min_x"]+bounds["max_x"])/2,
                      "y": (bounds["min_y"]+bounds["max_y"])/2, "z": 0.2},
         "extent": {"x": 5.0, "y": 5.0, "z": 0.2}},
    ]
    return {"ok": True, "map": map_name, "bounds": bounds,
            "road_points": cached["road_points"], "objects": actors,
            "static_targets": static_targets,
            "spectator": {"location": vector(spectator.location),
                          "rotation": {"yaw": spectator.rotation.yaw,
                                       "pitch": spectator.rotation.pitch}},
            "hero_id": hero.id if hero else None, "hero_lock": _hero_lock.is_set()}


def focus_actor(actor_id: int) -> dict:
    world = connect_world()
    actor = world.get_actor(actor_id)
    if not actor:
        raise RuntimeError(f"Actor {actor_id} is not running")
    kind = actor_record(actor)["kind"]
    transform = actor.get_transform()
    center = carla.Location(actor.bounding_box.location.x,
                            actor.bounding_box.location.y,
                            actor.bounding_box.location.z)
    transform.transform(center)
    extent = actor.bounding_box.extent
    world.debug.draw_box(carla.BoundingBox(center, extent), transform.rotation,
                         thickness=0.12, color=HIGHLIGHT_COLORS[kind],
                         life_time=8.0)
    focus_location(world, center, 8.0 if kind in ("walker", "prop") else 14.0,
                   3.5 if kind in ("walker", "prop") else 6.0)
    return {"ok": True, "actor_id": actor.id, "kind": kind,
            "location": vector(center)}


def focus_static(kind: str, name: str) -> dict:
    state = scene_state()
    target = next((item for item in state["static_targets"]
                   if item["kind"] == kind and item["name"] == name), None)
    if not target:
        raise RuntimeError(f"Unknown static target: {kind}/{name}")
    world = connect_world()
    loc, ext = target["location"], target["extent"]
    center = carla.Location(x=loc["x"], y=loc["y"], z=loc["z"])
    extent = carla.Vector3D(x=ext["x"], y=ext["y"], z=ext["z"])
    world.debug.draw_box(carla.BoundingBox(center, extent), carla.Rotation(),
                         thickness=0.16, color=HIGHLIGHT_COLORS[kind],
                         life_time=8.0)
    focus_location(world, center, 18.0, 12.0)
    return {"ok": True, "kind": kind, "name": name,
            "location": vector(center)}


def focus_bev(x: float, y: float) -> dict:
    world = connect_world()
    _hero_lock.clear()
    target = carla.Location(x=x, y=y, z=0.0)
    camera = carla.Location(x=x, y=y, z=55.0)
    world.get_spectator().set_transform(
        carla.Transform(camera, carla.Rotation(pitch=-90.0)))
    world.debug.draw_point(target + carla.Location(z=1.0), 0.35,
                           HIGHLIGHT_COLORS["road"], 5.0)
    return {"ok": True, "location": vector(target)}


def set_hero_lock(enabled: bool) -> dict:
    world = connect_world()
    hero = hero_actor(world)
    if enabled and not hero:
        raise RuntimeError("No vehicle with role_name=hero is running")
    _hero_lock.set() if enabled else _hero_lock.clear()
    return {"ok": True, "enabled": _hero_lock.is_set(),
            "hero_id": hero.id if hero else None}


def hero_follow_loop():
    while True:
        if _hero_lock.is_set():
            try:
                world = connect_world()
                hero = hero_actor(world)
                if not hero:
                    _hero_lock.clear()
                else:
                    transform = hero.get_transform()
                    forward = transform.get_forward_vector()
                    location = transform.location
                    camera = location + carla.Location(
                        x=-forward.x*10.0, y=-forward.y*10.0, z=5.5)
                    target = location + carla.Location(
                        x=forward.x*6.0, y=forward.y*6.0, z=1.2)
                    world.get_spectator().set_transform(
                        carla.Transform(camera, look_at(camera, target)))
            except Exception as exc:
                print(f"hero follow warning: {exc}", flush=True)
        time.sleep(0.1)


def apply_livery(payload: bytes, actor_id: int | None = None) -> dict:
    image, texture = decode_texture(payload, (2048, 2048))

    world = connect_world()
    actor = world.get_actor(actor_id) if actor_id else hero_actor(world)
    if not actor:
        raise RuntimeError("Select a running vehicle before applying a texture")
    if not actor.type_id.startswith("vehicle."):
        raise RuntimeError(f"Actor {actor.id} is not a vehicle")
    target = runtime_name_for_actor(world, actor)
    world.apply_color_texture_to_object(
        target, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "actor_id": actor.id, "type_id": actor.type_id,
            "object_name": target,
            "resolution": [image.width, image.height]}


def apply_road_texture(payload: bytes, scope: str) -> dict:
    image, texture = decode_texture(payload, (1024, 1024))
    world = connect_world()
    road_names = sorted(name for name in world.get_names_of_all_objects()
                        if name.startswith("Road_Road_"))
    if scope != "all":
        road_names = [name for name in road_names if name == scope]
    if not road_names:
        raise RuntimeError("No matching Road_Road surface objects found")
    world.apply_color_texture_to_objects(
        road_names, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "kind": "road", "object_count": len(road_names),
            "objects": road_names[:10],
            "resolution": [image.width, image.height]}


def apply_building_texture(payload: bytes, target: str) -> dict:
    image, texture = decode_texture(payload, (1024, 1024))
    world = connect_world()
    building_names = set(world.get_names_of_all_objects())
    if target not in building_names:
        raise RuntimeError(f"Building target is not present: {target}")
    if not target.startswith("BP_House16"):
        raise RuntimeError("Only the verified BP_House16 wall target is supported")
    world.apply_color_texture_to_object(
        target, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "kind": "building", "object_name": target,
            "material_slot": 0, "resolution": [image.width, image.height]}


def apply_environment_texture(payload: bytes, object_id: int) -> dict:
    image, texture = decode_texture(payload, (1024, 1024))
    world = connect_world()
    category, obj = find_environment(world, object_id)
    names = set(world.get_names_of_all_objects())
    candidates = [obj.name]
    for suffix in ("_SM_0", "_SM"):
        if obj.name.endswith(suffix):
            candidates.append(obj.name[:-len(suffix)])
    target = next((candidate for candidate in candidates if candidate in names), None)
    if target is None:
        target = next((name for name in names
                       if name.startswith(candidates[-1]) or candidates[-1].startswith(name)), None)
    if target is None:
        raise RuntimeError(
            f"The selected {category} object has no runtime material target: {obj.name}")
    world.apply_color_texture_to_object(
        target, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "kind": category, "object_id": str(obj.id),
            "object_name": target, "resolution": [image.width, image.height]}


def apply_pedestrian_texture(payload: bytes, actor_id: int | None = None) -> dict:
    image, texture = decode_texture(payload, (1024, 1024))
    world = connect_world()
    actor = world.get_actor(actor_id) if actor_id else None
    if not actor:
        walkers = list(world.get_actors().filter("walker.pedestrian.0001"))
        actor = walkers[-1] if walkers else None
    if not actor:
        raise RuntimeError("Select a running pedestrian before applying clothing")
    if actor.type_id != "walker.pedestrian.0001":
        raise RuntimeError(
            f"{actor.type_id} has no verified clothing slot; use walker.pedestrian.0001")
    target = runtime_name_for_actor(world, actor)
    world.apply_color_texture_to_object(
        target, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "kind": "pedestrian", "actor_id": actor.id,
            "object_name": target, "material_slots": [14],
            "resolution": [image.width, image.height]}


class Handler(BaseHTTPRequestHandler):
    def _headers(self, status=200):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", FRONTEND_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_OPTIONS(self):
        self._headers(204)

    def do_GET(self):
        request = urlparse(self.path)
        params = parse_qs(request.query)
        if request.path == "/catalog/thumbnail":
            try:
                payload = blueprint_thumbnail(params.get("blueprint", [""])[0])
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", FRONTEND_ORIGIN)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._headers(500)
                self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode())
            return
        self._headers()
        if request.path == "/catalog/categories":
            self.wfile.write(json.dumps(catalog_categories()).encode())
        elif request.path == "/catalog/objects":
            result = catalog_objects(
                params.get("category", ["buildings"])[0],
                params.get("q", [""])[0],
                max(0, int(params.get("offset", ["0"])[0])),
                min(200, max(1, int(params.get("limit", ["50"])[0]))))
            self.wfile.write(json.dumps(result).encode())
        elif request.path == "/catalog/blueprints":
            result = spawnable_blueprints(params.get("q", [""])[0], 200)
            self.wfile.write(json.dumps(result).encode())
        elif request.path == "/scene/state":
            self.wfile.write(json.dumps(scene_state()).encode())
        elif request.path == "/targets":
            kind = parse_qs(request.query).get("kind", [""])[0]
            prefix = {"road": "Road_Road_", "building": "BP_House"}.get(kind, "")
            names = sorted(name for name in connect_world().get_names_of_all_objects()
                           if prefix and name.startswith(prefix))
            self.wfile.write(json.dumps({"ok": True, "kind": kind,
                                         "count": len(names), "objects": names}).encode())
        else:
            self.wfile.write(json.dumps({"ok": True, "service": "carla-surface-bridge"}).encode())

    def do_POST(self):
        request = urlparse(self.path)
        if request.path not in ("/apply", "/apply/road", "/apply/building",
                                "/apply/environment",
                                "/apply/pedestrian", "/focus/actor",
                                "/focus/static", "/focus/bev",
                                "/focus/environment", "/camera/hero-lock",
                                "/objects/environment/visibility",
                                "/objects/spawn", "/objects/update",
                                "/objects/duplicate", "/objects/delete",
                                "/scenario/compile", "/scenario/run"):
            self._headers(404)
            self.wfile.write(b'{"ok":false,"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length)
            if request.path in ("/scenario/compile", "/scenario/run"):
                data = json.loads(payload or b"{}")
                result = compile_scenario(data, request.path.endswith("/run"))
            elif request.path == "/focus/actor":
                data = json.loads(payload or b"{}")
                result = focus_actor(int(data["actor_id"]))
            elif request.path == "/focus/static":
                data = json.loads(payload or b"{}")
                result = focus_static(str(data["kind"]), str(data["name"]))
            elif request.path == "/focus/environment":
                data = json.loads(payload or b"{}")
                result = focus_environment(int(data["object_id"]))
            elif request.path == "/focus/bev":
                data = json.loads(payload or b"{}")
                result = focus_bev(float(data["x"]), float(data["y"]))
            elif request.path == "/camera/hero-lock":
                data = json.loads(payload or b"{}")
                result = set_hero_lock(bool(data.get("enabled")))
            elif request.path == "/objects/environment/visibility":
                data = json.loads(payload or b"{}")
                result = set_environment_visibility(
                    int(data["object_id"]), bool(data.get("visible", True)))
            elif request.path == "/objects/spawn":
                data = json.loads(payload or b"{}")
                result = spawn_object(str(data["blueprint_id"]), data.get("transform", {}))
            elif request.path == "/objects/update":
                data = json.loads(payload or b"{}")
                result = update_actor(int(data["actor_id"]), data.get("transform", {}))
            elif request.path == "/objects/duplicate":
                data = json.loads(payload or b"{}")
                result = duplicate_actor(int(data["actor_id"]))
            elif request.path == "/objects/delete":
                data = json.loads(payload or b"{}")
                result = delete_actor(int(data["actor_id"]))
            elif request.path == "/apply/road":
                scope = parse_qs(request.query).get("scope", ["all"])[0]
                result = apply_road_texture(payload, scope)
            elif request.path == "/apply/building":
                target = parse_qs(request.query).get("target", ["BP_House16"])[0]
                result = apply_building_texture(payload, target)
            elif request.path == "/apply/environment":
                object_id = int(parse_qs(request.query)["object_id"][0])
                result = apply_environment_texture(payload, object_id)
            elif request.path == "/apply/pedestrian":
                actor_id = parse_qs(request.query).get("actor_id", [None])[0]
                result = apply_pedestrian_texture(
                    payload, int(actor_id) if actor_id else None)
            else:
                actor_id = parse_qs(request.query).get("actor_id", [None])[0]
                result = apply_livery(payload, int(actor_id) if actor_id else None)
            self._headers()
            self.wfile.write(json.dumps(result).encode())
        except Exception as exc:
            self._headers(500)
            self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode())

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    print(f"CARLA livery bridge listening on http://{HOST}:{PORT}", flush=True)
    threading.Thread(target=hero_follow_loop, daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
