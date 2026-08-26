from __future__ import annotations

import fnmatch
import json
import math
import time
from pathlib import Path
from typing import Any

from .metrics import KinematicState, distance, evaluate, ttc
from .models import ActorSpec, ProceduralAssetSpec, ScenarioResult, ScenarioSpec


class CarlaUnavailable(RuntimeError):
    pass


class CarlaAdapter:
    """Narrow CARLA 0.9.16 execution boundary.

    Importing this module is safe without CARLA. The external module is loaded
    only when connect/run is requested, so generation and tests remain offline.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 2000, timeout_s: float = 10.0):
        self.host, self.port, self.timeout_s = host, port, timeout_s

    def _module(self) -> Any:
        try:
            import carla  # type: ignore
        except ImportError as exc:
            raise CarlaUnavailable(
                "CARLA Python module is unavailable; install the matching wheel or set PYTHONPATH"
            ) from exc
        return carla

    def run(self, spec: ScenarioSpec, output_dir: Path, render: bool = False) -> ScenarioResult:
        carla = self._module()
        client = carla.Client(self.host, self.port)
        client.set_timeout(self.timeout_s)
        world = client.get_world()
        if spec.map_name.lower() not in world.get_map().name.lower():
            world = client.load_world(spec.map_name)
        original = world.get_settings()
        actors: list[Any] = []
        collision = {"hit": False}
        trace: list[dict[str, Any]] = []
        min_distance = math.inf
        min_ttc: float | None = None
        elapsed = 0.0
        try:
            settings = world.get_settings()
            settings.synchronous_mode = True
            settings.fixed_delta_seconds = 0.05
            world.apply_settings(settings)
            world.set_weather(carla.WeatherParameters(
                cloudiness=spec.environment.cloudiness,
                precipitation=spec.environment.precipitation,
                fog_density=spec.environment.fog_density,
                sun_altitude_angle=spec.environment.sun_altitude_angle,
            ))
            spawn_points = world.get_map().get_spawn_points()
            ego = self._spawn(world, spec.ego, spawn_points)
            actors.append(ego)
            adversaries = [self._spawn(world, a, spawn_points) for a in spec.adversaries]
            actors.extend(adversaries)
            # Newly spawned physics actors report the origin through RPC until
            # their first world tick. Asset placement must use the initialized
            # vehicle pose, not that transient placeholder transform.
            world.tick()
            generated_assets: list[Any] = []
            for asset_spec in spec.generated_assets:
                spawned = self._spawn_generated_asset(carla, world, ego, asset_spec)
                generated_assets.extend(spawned)
                actors.extend(spawned)
            sensor_bp = world.get_blueprint_library().find("sensor.other.collision")
            sensor = world.spawn_actor(sensor_bp, carla.Transform(), attach_to=ego)
            sensor.listen(lambda _: collision.__setitem__("hit", True))
            actors.append(sensor)
            if render:
                camera_bp = world.get_blueprint_library().find("sensor.camera.rgb")
                camera_bp.set_attribute("image_size_x", "1280")
                camera_bp.set_attribute("image_size_y", "720")
                camera_bp.set_attribute("fov", "90")
                camera_transform = carla.Transform(
                    carla.Location(x=-7.5, z=3.0), carla.Rotation(pitch=-12.0)
                )
                camera = world.spawn_actor(camera_bp, camera_transform, attach_to=ego)
                frames_dir = output_dir / spec.scenario_id / "frames"
                frames_dir.mkdir(parents=True, exist_ok=True)

                def save_frame(image: Any) -> None:
                    if image.frame % 5 == 0:
                        image.save_to_disk(str(frames_dir / f"{image.frame:08d}.png"))

                camera.listen(save_frame)
                actors.append(camera)
            ego.set_autopilot(spec.family != "road_hazard")
            for adv, adv_spec in zip(adversaries, spec.adversaries):
                if adv_spec.behavior == "autopilot":
                    adv.set_autopilot(True)
            steps = int(spec.oracle.max_duration_s / settings.fixed_delta_seconds)
            triggered: set[int] = set()
            for frame in range(steps):
                if spec.family == "road_hazard":
                    ego.apply_control(carla.VehicleControl(throttle=0.55, steer=0.0))
                if render:
                    self._follow_spectator(carla, world, ego)
                world.tick()
                if render:
                    time.sleep(settings.fixed_delta_seconds)
                elapsed = (frame + 1) * settings.fixed_delta_seconds
                ego_state = self._state(ego)
                for index, (adv, adv_spec) in enumerate(zip(adversaries, spec.adversaries)):
                    adv_state = self._state(adv)
                    d = distance(ego_state, adv_state)
                    current_ttc = ttc(ego_state, adv_state)
                    min_distance = min(min_distance, d)
                    if current_ttc is not None:
                        min_ttc = current_ttc if min_ttc is None else min(min_ttc, current_ttc)
                    if index not in triggered and d <= (adv_spec.trigger_distance_m or 0.0):
                        self._trigger(carla, adv, adv_spec)
                        triggered.add(index)
                    trace.append({"frame": frame, "t": elapsed, "distance_m": d, "ttc_s": current_ttc})
                for asset in generated_assets:
                    asset_state = self._state(asset)
                    d = distance(ego_state, asset_state)
                    current_ttc = ttc(ego_state, asset_state)
                    min_distance = min(min_distance, d)
                    if current_ttc is not None:
                        min_ttc = current_ttc if min_ttc is None else min(min_ttc, current_ttc)
                    trace.append({
                        "frame": frame, "t": elapsed, "distance_m": d,
                        "ttc_s": current_ttc, "generated_asset_id": asset.id,
                    })
                if collision["hit"]:
                    break
            output_dir.mkdir(parents=True, exist_ok=True)
            trace_path = output_dir / f"{spec.scenario_id}.trace.json"
            trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
            return evaluate(spec.scenario_id, spec.oracle, collision["hit"], min_ttc,
                            min_distance, elapsed, str(trace_path))
        finally:
            # Sensor callbacks run on streaming threads. Stop every sensor first,
            # then advance one synchronous frame so callbacks drain before any
            # attached actor is destroyed.
            for actor in actors:
                try:
                    if getattr(actor, "type_id", "").startswith("sensor."):
                        actor.stop()
                    elif getattr(actor, "type_id", "").startswith("vehicle."):
                        actor.set_autopilot(False)
                except RuntimeError:
                    pass
            # save_to_disk runs on sensor streaming threads. Give an in-flight
            # PNG write time to finish after stop() before attached actors and
            # the scene-capture resource are destroyed.
            if render:
                time.sleep(0.25)
            try:
                if world.get_settings().synchronous_mode:
                    world.tick()
            except RuntimeError:
                pass
            actor_ids = [actor.id for actor in actors if getattr(actor, "is_alive", False)]
            if actor_ids:
                client.apply_batch([carla.command.DestroyActor(actor_id) for actor_id in actor_ids])
            world.apply_settings(original)

    @staticmethod
    def _spawn_generated_asset(
        carla: Any, world: Any, ego: Any, spec: ProceduralAssetSpec
    ) -> list[Any]:
        if spec.shape != "metal_pipes":
            raise RuntimeError(f"unsupported generated asset shape: {spec.shape}")
        library = world.get_blueprint_library()
        blueprint = library.find("static.prop.mesh")
        required = {"mesh_path", "mass", "scale_x", "scale_y", "scale_z"}
        available = {attribute.id for attribute in blueprint}
        missing = required - available
        if missing:
            raise RuntimeError(
                "CARLA procedural asset extension is not installed; missing attributes: "
                + ", ".join(sorted(missing))
            )
        waypoint = world.get_map().get_waypoint(ego.get_location(), project_to_road=True)
        candidates = waypoint.next(spec.distance_ahead_m)
        if not candidates:
            raise RuntimeError("no road waypoint available for generated asset placement")
        base = candidates[0].transform
        length, diameter, _ = spec.dimensions_m
        # UE BasicShapes/Cylinder is 1 m high and 1 m in diameter. Rotate its
        # local Z axis onto the road plane and scale each axis independently.
        blueprint.set_attribute("mesh_path", "/Engine/BasicShapes/Cylinder.Cylinder")
        blueprint.set_attribute("mass", str(spec.mass_kg / spec.count))
        blueprint.set_attribute("scale_x", str(diameter))
        blueprint.set_attribute("scale_y", str(diameter))
        blueprint.set_attribute("scale_z", str(length))
        spawned: list[Any] = []
        columns = spec.count
        for index in range(spec.count):
            row, column = divmod(index, columns)
            lateral = spec.lateral_offset_m + (column - (columns - 1) / 2.0) * diameter * 1.15
            vertical = diameter * (0.55 + row * 0.9)
            location = base.location + base.get_right_vector() * lateral + carla.Location(z=vertical)
            rotation = carla.Rotation(
                pitch=base.rotation.pitch + 90.0,
                yaw=base.rotation.yaw + (index % 2) * 2.0 - 1.0,
                roll=base.rotation.roll,
            )
            actor = world.try_spawn_actor(blueprint, carla.Transform(location, rotation))
            if actor is None:
                for previous in spawned:
                    previous.destroy()
                raise RuntimeError(f"failed to spawn generated pipe {index}")
            spawned.append(actor)
        return spawned

    @staticmethod
    def _spawn(world: Any, spec: ActorSpec, spawn_points: list[Any]) -> Any:
        library = world.get_blueprint_library()
        matches = [bp for bp in library if fnmatch.fnmatch(bp.id, spec.blueprint)]
        if not matches:
            raise RuntimeError(f"no blueprint matches {spec.blueprint}")
        transform = spawn_points[spec.spawn_index % len(spawn_points)]
        actor = world.try_spawn_actor(matches[0], transform)
        if actor is None:
            raise RuntimeError(f"spawn failed for {spec.role} at index {spec.spawn_index}")
        velocity = transform.get_forward_vector() * spec.speed_mps
        actor.set_target_velocity(velocity)
        return actor

    @staticmethod
    def _state(actor: Any) -> KinematicState:
        p, v = actor.get_location(), actor.get_velocity()
        return KinematicState(p.x, p.y, v.x, v.y)

    @staticmethod
    def _follow_spectator(carla: Any, world: Any, ego: Any) -> None:
        transform = ego.get_transform()
        location = (
            transform.location
            - transform.get_forward_vector() * 10.0
            + carla.Location(z=5.0)
        )
        world.get_spectator().set_transform(carla.Transform(
            location,
            carla.Rotation(pitch=-17.0, yaw=transform.rotation.yaw),
        ))

    @staticmethod
    def _trigger(carla: Any, actor: Any, spec: ActorSpec) -> None:
        if spec.behavior == "hard_brake":
            actor.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
        elif spec.behavior == "cut_in":
            control = actor.get_control()
            control.steer = -0.45 if spec.lateral_offset_m <= 0 else 0.45
            control.throttle = 0.55
            actor.apply_control(control)
        elif spec.behavior == "cross_road" and hasattr(actor, "set_target_velocity"):
            transform = actor.get_transform()
            actor.set_target_velocity(transform.get_right_vector() * spec.speed_mps)
