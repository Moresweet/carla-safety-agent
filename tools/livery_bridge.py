#!/usr/bin/env python3
"""Local HTTP bridge for applying browser-composed liveries to CARLA."""

import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import carla
from PIL import Image


HOST = "127.0.0.1"
PORT = 8765


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
    client = carla.Client(HOST, 2000)
    client.set_timeout(20.0)
    return client.get_world()


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
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_OPTIONS(self):
        self._headers(204)

    def do_GET(self):
        request = urlparse(self.path)
        self._headers()
        if request.path == "/targets":
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
                                "/apply/pedestrian"):
            self._headers(404)
            self.wfile.write(b'{"ok":false,"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length)
            if request.path == "/apply/road":
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
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
