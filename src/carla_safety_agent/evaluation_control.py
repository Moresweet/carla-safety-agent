"""Frame-boundary scene control for closed-loop CARLA evaluations.

The evaluator is the only client allowed to mutate a synchronous CARLA world.
The web bridge exchanges atomic JSON commands and snapshots through a runtime
directory, so editor requests never compete for the simulator's tick lock.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import carla
from PIL import Image


ENVIRONMENT_LABELS = {
    "buildings": carla.CityObjectLabel.Buildings, "bridges": carla.CityObjectLabel.Bridge,
    "walls": carla.CityObjectLabel.Walls, "fences": carla.CityObjectLabel.Fences,
    "roads": carla.CityObjectLabel.Roads, "road_lines": carla.CityObjectLabel.RoadLines,
    "sidewalks": carla.CityObjectLabel.Sidewalks, "ground": carla.CityObjectLabel.Ground,
    "terrain": carla.CityObjectLabel.Terrain, "vegetation": carla.CityObjectLabel.Vegetation,
    "water": carla.CityObjectLabel.Water, "poles": carla.CityObjectLabel.Poles,
    "guard_rails": carla.CityObjectLabel.GuardRail,
    "traffic_signs": carla.CityObjectLabel.TrafficSigns,
    "traffic_lights": carla.CityObjectLabel.TrafficLight,
    "parked_cars": carla.CityObjectLabel.Car, "dynamic_props": carla.CityObjectLabel.Dynamic,
    "static_props": carla.CityObjectLabel.Static,
}


def _vector(value: Any) -> dict[str, float]:
    return {"x": round(value.x, 3), "y": round(value.y, 3), "z": round(value.z, 3)}


def _actor_record(actor: carla.Actor, origin: str = "evaluation") -> dict[str, Any]:
    kind = ("walker" if actor.type_id.startswith("walker.") else
            "prop" if actor.type_id.startswith("static.prop.") else "vehicle")
    transform = actor.get_transform()
    return {
        "key": f"actor:{actor.id}", "id": actor.id, "source": "actor",
        "category": {"vehicle": "vehicles", "walker": "pedestrians",
                     "prop": "spawned_props"}[kind],
        "group": "dynamic", "kind": kind, "name": actor.type_id,
        "label": f"{actor.type_id} · #{actor.id}",
        "location": _vector(transform.location),
        "rotation": {"pitch": transform.rotation.pitch,
                     "yaw": transform.rotation.yaw,
                     "roll": transform.rotation.roll},
        "extent": _vector(actor.bounding_box.extent),
        "hero": actor.attributes.get("role_name") == "hero",
        "origin": origin,
    }


def _texture_from_file(path: Path) -> carla.TextureColor:
    image = Image.open(path).convert("RGBA")
    if image.size != (2048, 2048):
        image = image.resize((2048, 2048), Image.Resampling.LANCZOS)
    texture = carla.TextureColor(image.width, image.height)
    pixels = image.load()
    for x in range(image.width):
        for y in range(image.height):
            r, g, b, a = pixels[x, image.height - 1 - y]
            texture.set(x, y, carla.Color(r, g, b, a))
    return texture


def _runtime_vehicle_name(world: carla.World, actor: carla.Actor) -> str:
    names = sorted(world.get_names_of_all_objects())
    actor_token = str(actor.id)
    matches = [name for name in names if actor_token in name and name.startswith("BP_")]
    if matches:
        return matches[-1]
    prefixes = {
        "vehicle.tesla.model3": "BP_TeslaM3_C_",
        "vehicle.carlamotors.european_hgv": "BP_European_HGV_C_",
        "vehicle.lincoln.mkz_2020": "BP_Lincoln2020_C_",
        "vehicle.dodge.charger_2020": "BP_Charger2020_C_",
        "vehicle.mini.cooper_s_2021": "BP_Mini2021_C_",
        "vehicle.mercedes.coupe_2020": "BP_MercedesCCC_C_",
        "vehicle.audi.tt": "BP_AudiTT_C_",
    }
    prefix = prefixes.get(actor.type_id)
    matches = [name for name in names if prefix and name.startswith(prefix)]
    if matches:
        same_type_ids = sorted(item.id for item in world.get_actors().filter(actor.type_id))
        ordinal = same_type_ids.index(actor.id)
        if ordinal < len(matches):
            return matches[ordinal]
    blueprint_token = actor.type_id.rsplit(".", 1)[-1].replace("_", "").casefold()
    matches = [name for name in names
               if blueprint_token and blueprint_token in name.replace("_", "").casefold()
               and name.startswith("BP_")]
    if len(matches) == 1:
        return matches[0]
    raise RuntimeError(
        f"Runtime mesh identity is ambiguous for actor {actor.id} ({actor.type_id}); "
        f"candidates={matches[:8]}")


class EvaluationControl:
    """Consume editor commands from the process that owns synchronous ticks."""

    def __init__(self, runtime_dir: str | Path | None = None) -> None:
        configured = runtime_dir or os.environ.get("CSA_EVALUATION_CONTROL_DIR")
        self.root = Path(configured) if configured else None
        self.last_snapshot = 0.0
        self.blueprints: list[str] | None = None
        self.road_points: list[dict[str, float]] | None = None
        self.user_actor_ids: set[int] = set()
        self.camera_target: tuple[str, Any] | None = None
        if self.root:
            (self.root / "commands").mkdir(parents=True, exist_ok=True)
            (self.root / "results").mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def on_frame(self, world: carla.World) -> None:
        if not self.root:
            return
        self._process_commands(world)
        self._apply_camera(world)
        now = time.monotonic()
        if now - self.last_snapshot >= 0.35:
            self._write_snapshot(world)
            self.last_snapshot = now

    def _atomic_json(self, target: Path, value: Any) -> None:
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(value), encoding="utf-8")
        temporary.replace(target)

    def _write_snapshot(self, world: carla.World) -> None:
        actors = [_actor_record(actor, "user" if actor.id in self.user_actor_ids else "evaluation")
                  for actor in world.get_actors()
                  if actor.type_id.startswith(("vehicle.", "walker.", "static.prop."))]
        if self.blueprints is None:
            patterns = ("vehicle.*", "walker.pedestrian.*", "static.prop.*")
            self.blueprints = sorted({bp.id for pattern in patterns
                                      for bp in world.get_blueprint_library().filter(pattern)})
        if self.road_points is None:
            points = [_vector(waypoint.transform.location)
                      for waypoint in world.get_map().generate_waypoints(20.0)]
            stride = max(1, math.ceil(len(points) / 2500))
            self.road_points = points[::stride]
        locations = self.road_points or [item["location"] for item in actors]
        if locations:
            margin = 60.0
            bounds = {"min_x": min(v["x"] for v in locations)-margin,
                      "max_x": max(v["x"] for v in locations)+margin,
                      "min_y": min(v["y"] for v in locations)-margin,
                      "max_y": max(v["y"] for v in locations)+margin}
        else:
            bounds = {"min_x": -100, "max_x": 100, "min_y": -100, "max_y": 100}
        spectator = world.get_spectator().get_transform()
        self._atomic_json(self.root / "state.json", {
            "schema_version": "carla-safety-live-state/0.1",
            "updated_at": time.time(), "map": world.get_map().name,
            "bounds": bounds, "objects": actors, "blueprints": self.blueprints,
            "road_points": self.road_points,
            "spectator": {"location": _vector(spectator.location),
                          "rotation": {"yaw": spectator.rotation.yaw,
                                       "pitch": spectator.rotation.pitch}},
        })

    def _process_commands(self, world: carla.World) -> None:
        for path in sorted((self.root / "commands").glob("*.json"))[:8]:
            try:
                command = json.loads(path.read_text(encoding="utf-8"))
                result = self._execute(world, command["action"], command.get("payload", {}))
                response = {"ok": True, **result}
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
            self._atomic_json(self.root / "results" / path.name, response)
            path.unlink(missing_ok=True)

    def _execute(self, world: carla.World, action: str, data: dict[str, Any]) -> dict[str, Any]:
        if action == "focus_actor":
            actor_id = int(data["actor_id"])
            actor = world.get_actor(actor_id)
            if not actor:
                raise RuntimeError(f"Actor {actor_id} is not running")
            self.camera_target = ("actor", actor_id)
            return {"actor_id": actor_id, "kind": _actor_record(actor)["kind"]}
        if action == "focus_bev":
            self.camera_target = ("location", (float(data["x"]), float(data["y"]), 0.0))
            return {"location": {"x": float(data["x"]), "y": float(data["y"]), "z": 0.0}}
        if action == "focus_environment":
            object_id = int(data["object_id"])
            for label in ENVIRONMENT_LABELS.values():
                match = next((obj for obj in world.get_environment_objects(label)
                              if int(obj.id) == object_id), None)
                if match:
                    location = match.bounding_box.location
                    self.camera_target = ("location", (location.x, location.y, location.z))
                    return {"object_id": str(match.id), "name": match.name,
                            "location": _vector(location)}
            raise RuntimeError(f"Environment object {object_id} was not found")
        if action == "catalog_environment":
            category = str(data["category"])
            if category not in ENVIRONMENT_LABELS:
                raise RuntimeError(f"Unknown environment category: {category}")
            query = str(data.get("query", "")).casefold()
            objects = world.get_environment_objects(ENVIRONMENT_LABELS[category])
            records = []
            for obj in objects:
                if query and query not in obj.name.casefold() and query not in str(obj.id):
                    continue
                box = obj.bounding_box
                records.append({"key": f"environment:{obj.id}", "id": str(obj.id),
                    "source": "environment", "category": category, "group": "environment",
                    "kind": "road" if category in {"roads", "road_lines", "sidewalks", "ground", "terrain", "water"} else "building",
                    "name": obj.name, "label": f"{obj.name} · {str(obj.id)[-6:]}",
                    "location": _vector(box.location), "extent": _vector(box.extent),
                    "rotation": {"pitch": obj.transform.rotation.pitch,
                                 "yaw": obj.transform.rotation.yaw,
                                 "roll": obj.transform.rotation.roll}})
            offset, limit = int(data.get("offset", 0)), int(data.get("limit", 50))
            return {"category": category, "total": len(records), "offset": offset,
                    "limit": limit, "objects": records[offset:offset+limit]}
        if action == "environment_visibility":
            object_id = int(data["object_id"])
            enabled = bool(data.get("visible", True))
            for label in ENVIRONMENT_LABELS.values():
                match = next((obj for obj in world.get_environment_objects(label)
                              if int(obj.id) == object_id), None)
                if match:
                    world.enable_environment_objects({match.id}, enabled)
                    return {"id": str(match.id), "visible": enabled}
            raise RuntimeError(f"Environment object {object_id} was not found")
        if action == "spawn":
            blueprint_id = str(data["blueprint_id"])
            if not blueprint_id.startswith(("vehicle.", "walker.", "static.prop.")):
                raise RuntimeError("Unsupported blueprint type")
            blueprint = world.get_blueprint_library().find(blueprint_id)
            spec = data.get("transform", {})
            loc, rot = spec.get("location", {}), spec.get("rotation", {})
            location = carla.Location(x=float(loc.get("x", 0)), y=float(loc.get("y", 0)),
                                      z=float(loc.get("z", 1)))
            if spec.get("snap_to_ground"):
                waypoint = world.get_map().get_waypoint(location, project_to_road=True,
                    lane_type=carla.LaneType.Driving | carla.LaneType.Sidewalk)
                if waypoint:
                    location.z = waypoint.transform.location.z + (
                        3.0 if blueprint_id.startswith("vehicle.") else 1.0)
            transform = carla.Transform(location, carla.Rotation(
                pitch=float(rot.get("pitch", 0)), yaw=float(rot.get("yaw", 0)),
                roll=float(rot.get("roll", 0))))
            actor = world.spawn_actor(blueprint, transform)
            self.user_actor_ids.add(actor.id)
            if blueprint_id.startswith("vehicle."):
                actor.set_target_velocity(carla.Vector3D())
                actor.set_target_angular_velocity(carla.Vector3D())
                actor.apply_control(carla.VehicleControl(hand_brake=True))
            record = _actor_record(actor, "user")
            record["location"] = _vector(transform.location)
            record["rotation"] = {"pitch": transform.rotation.pitch,
                                  "yaw": transform.rotation.yaw,
                                  "roll": transform.rotation.roll}
            return {"object": record}
        actor_id = int(data.get("actor_id", 0))
        actor = world.get_actor(actor_id)
        if not actor:
            raise RuntimeError(f"Actor {actor_id} is not running")
        if action == "update":
            current = actor.get_transform()
            spec = data.get("transform", {})
            loc, rot = spec.get("location", {}), spec.get("rotation", {})
            actor.set_transform(carla.Transform(carla.Location(
                x=float(loc.get("x", current.location.x)),
                y=float(loc.get("y", current.location.y)),
                z=float(loc.get("z", current.location.z))), carla.Rotation(
                pitch=float(rot.get("pitch", current.rotation.pitch)),
                yaw=float(rot.get("yaw", current.rotation.yaw)),
                roll=float(rot.get("roll", current.rotation.roll)))))
            return {"object": _actor_record(actor, "user" if actor.id in self.user_actor_ids else "evaluation")}
        if action == "delete":
            type_id = actor.type_id
            actor.destroy()
            self.user_actor_ids.discard(actor_id)
            return {"actor_id": actor_id, "type_id": type_id}
        if action == "duplicate":
            transform = actor.get_transform()
            return self._execute(world, "spawn", {"blueprint_id": actor.type_id,
                "transform": {"location": {"x": transform.location.x+3,
                                             "y": transform.location.y+3,
                                             "z": transform.location.z+0.5},
                              "rotation": {"pitch": transform.rotation.pitch,
                                           "yaw": transform.rotation.yaw,
                                           "roll": transform.rotation.roll}}})
        if action == "apply_vehicle_texture":
            texture_path = Path(str(data["texture_path"]))
            if self.root not in texture_path.parents or not texture_path.is_file():
                raise RuntimeError("Texture payload is outside the evaluation workspace")
            if not actor.type_id.startswith("vehicle."):
                raise RuntimeError(f"Actor {actor.id} is not a vehicle")
            target = _runtime_vehicle_name(world, actor)
            world.apply_color_texture_to_object(
                target, carla.MaterialParameter.Diffuse, _texture_from_file(texture_path))
            texture_path.unlink(missing_ok=True)
            return {"actor_id": actor.id, "type_id": actor.type_id,
                    "object_name": target, "resolution": [2048, 2048]}
        raise RuntimeError(f"Unsupported evaluation edit: {action}")

    def _apply_camera(self, world: carla.World) -> None:
        if not self.camera_target:
            return
        mode, value = self.camera_target
        if mode == "actor":
            actor = world.get_actor(int(value))
            if not actor:
                self.camera_target = None
                return
            target = actor.get_location()
        else:
            target = carla.Location(x=value[0], y=value[1], z=value[2])
        camera = target + carla.Location(x=-12, y=-12, z=8)
        dx, dy, dz = target.x-camera.x, target.y-camera.y, target.z-camera.z
        rotation = carla.Rotation(pitch=math.degrees(math.atan2(dz, (dx*dx+dy*dy)**0.5)),
                                  yaw=math.degrees(math.atan2(dy, dx)))
        world.get_spectator().set_transform(carla.Transform(camera, rotation))
        if mode == "actor":
            actor = world.get_actor(int(value))
            transform = actor.get_transform()
            center = carla.Location(actor.bounding_box.location.x,
                                    actor.bounding_box.location.y,
                                    actor.bounding_box.location.z)
            transform.transform(center)
            world.debug.draw_box(carla.BoundingBox(center, actor.bounding_box.extent), transform.rotation,
                                 thickness=0.12, color=carla.Color(0, 220, 255), life_time=0.0)
