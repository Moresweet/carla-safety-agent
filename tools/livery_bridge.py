#!/usr/bin/env python3
"""Local HTTP bridge for applying browser-composed liveries to CARLA."""

import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import carla
from PIL import Image


HOST = "127.0.0.1"
PORT = 8765


def apply_livery(payload: bytes) -> dict:
    image = Image.open(io.BytesIO(payload)).convert("RGBA")
    if image.size != (2048, 2048):
        image = image.resize((2048, 2048), Image.Resampling.LANCZOS)

    client = carla.Client(HOST, 2000)
    client.set_timeout(20.0)
    world = client.get_world()
    heroes = [actor for actor in world.get_actors().filter("vehicle.*")
              if actor.attributes.get("role_name") == "hero"]
    if not heroes:
        raise RuntimeError("No vehicle with role_name=hero is running")

    hero = heroes[0]
    actor_names = world.get_names_of_all_objects()
    tesla_names = [name for name in actor_names if name.startswith("BP_TeslaM3_C_")]
    if hero.type_id != "vehicle.tesla.model3" or not tesla_names:
        raise RuntimeError("The active hero is not a Tesla Model 3")

    texture = carla.TextureColor(image.width, image.height)
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            texture.set(x, y, carla.Color(r, g, b, a))

    target = tesla_names[-1]
    world.apply_color_texture_to_object(
        target, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "actor_id": hero.id, "object_name": target,
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
        self._headers()
        self.wfile.write(json.dumps({"ok": True, "service": "carla-livery-bridge"}).encode())

    def do_POST(self):
        if self.path != "/apply":
            self._headers(404)
            self.wfile.write(b'{"ok":false,"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            result = apply_livery(self.rfile.read(length))
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
