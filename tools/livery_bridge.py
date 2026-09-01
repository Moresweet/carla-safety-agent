#!/usr/bin/env python3
"""Local HTTP bridge for applying browser-composed liveries to CARLA."""

import io
import json
import os
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import carla
from PIL import Image


HOST = "127.0.0.1"
PORT = int(os.environ.get("BRIDGE_PORT", "8765"))
CARLA_PORT = int(os.environ.get("CARLA_PORT", "2000"))
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
HIGHLIGHT_COLORS = {
    "vehicle": carla.Color(0, 170, 255),
    "walker": carla.Color(255, 200, 0),
    "building": carla.Color(190, 80, 255),
    "road": carla.Color(255, 70, 70),
}
_hero_lock = threading.Event()
_map_cache = {}


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
    kind = "walker" if actor.type_id.startswith("walker.") else "vehicle"
    extent = actor.bounding_box.extent
    return {"key": f"actor:{actor.id}", "id": actor.id, "kind": kind,
            "name": actor.type_id, "label": f"{actor.type_id} · #{actor.id}",
            "location": vector(actor.get_location()),
            "extent": vector(extent),
            "hero": actor.attributes.get("role_name") == "hero"}


def scene_state() -> dict:
    world = connect_world()
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
    kind = "walker" if actor.type_id.startswith("walker.") else "vehicle"
    transform = actor.get_transform()
    center = carla.Location(actor.bounding_box.location.x,
                            actor.bounding_box.location.y,
                            actor.bounding_box.location.z)
    transform.transform(center)
    extent = actor.bounding_box.extent
    world.debug.draw_box(carla.BoundingBox(center, extent), transform.rotation,
                         thickness=0.12, color=HIGHLIGHT_COLORS[kind],
                         life_time=8.0)
    focus_location(world, center, 8.0 if kind == "walker" else 14.0,
                   3.5 if kind == "walker" else 6.0)
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


def apply_livery(payload: bytes) -> dict:
    image, texture = decode_texture(payload, (2048, 2048))

    world = connect_world()
    heroes = [actor for actor in world.get_actors().filter("vehicle.*")
              if actor.attributes.get("role_name") == "hero"]
    if not heroes:
        raise RuntimeError("No vehicle with role_name=hero is running")

    hero = heroes[0]
    actor_names = world.get_names_of_all_objects()
    tesla_names = [name for name in actor_names if name.startswith("BP_TeslaM3_C_")]
    if hero.type_id != "vehicle.tesla.model3" or not tesla_names:
        raise RuntimeError("The active hero is not a Tesla Model 3")

    target = tesla_names[-1]
    world.apply_color_texture_to_object(
        target, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "actor_id": hero.id, "object_name": target,
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


def apply_pedestrian_texture(payload: bytes) -> dict:
    image, texture = decode_texture(payload, (1024, 1024))
    world = connect_world()
    walkers = list(world.get_actors().filter("walker.pedestrian.0001"))
    names = sorted(name for name in world.get_names_of_all_objects()
                   if name.startswith("BP_Walker_Female1_v1_C_"))
    if not walkers or not names:
        raise RuntimeError("No walker.pedestrian.0001 is running")
    target = names[-1]
    world.apply_color_texture_to_object(
        target, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "kind": "pedestrian", "actor_id": walkers[-1].id,
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
        self._headers()
        if request.path == "/scene/state":
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
                                "/apply/pedestrian", "/focus/actor",
                                "/focus/static", "/focus/bev",
                                "/camera/hero-lock"):
            self._headers(404)
            self.wfile.write(b'{"ok":false,"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length)
            if request.path == "/focus/actor":
                data = json.loads(payload or b"{}")
                result = focus_actor(int(data["actor_id"]))
            elif request.path == "/focus/static":
                data = json.loads(payload or b"{}")
                result = focus_static(str(data["kind"]), str(data["name"]))
            elif request.path == "/focus/bev":
                data = json.loads(payload or b"{}")
                result = focus_bev(float(data["x"]), float(data["y"]))
            elif request.path == "/camera/hero-lock":
                data = json.loads(payload or b"{}")
                result = set_hero_lock(bool(data.get("enabled")))
            elif request.path == "/apply/road":
                scope = parse_qs(request.query).get("scope", ["all"])[0]
                result = apply_road_texture(payload, scope)
            elif request.path == "/apply/building":
                target = parse_qs(request.query).get("target", ["BP_House16"])[0]
                result = apply_building_texture(payload, target)
            elif request.path == "/apply/pedestrian":
                result = apply_pedestrian_texture(payload)
            else:
                result = apply_livery(payload)
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
