"""Project-owned closed-loop executor for generated safety scenarios."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

from .carla_adapter import CarlaAdapter
from .evaluation_control import EvaluationControl
from .io import scenario_from_dict
from .metrics import distance, evaluate, ttc
from .opendrive import build_opendrive
from leaderboard.autoagents.autonomous_agent import RoadOption


class NativeSensorRig:
    def __init__(self, carla: Any, world: Any, ego: Any, interface: Any) -> None:
        self.carla, self.world, self.ego, self.interface = carla, world, ego, interface
        self.sensors: list[Any] = []
        self.has_speedometer = False

    def setup(self, specs: list[dict[str, Any]]) -> None:
        import numpy as np

        for spec in specs:
            sensor_type, tag = spec["type"], spec["id"]
            if sensor_type == "sensor.speedometer":
                self.interface.register_sensor(tag, sensor_type, self.ego)
                self.has_speedometer = True
                continue
            blueprint = self.world.get_blueprint_library().find(sensor_type)
            for source, target in (("width", "image_size_x"), ("height", "image_size_y"),
                                   ("fov", "fov"), ("sensor_tick", "sensor_tick")):
                if source in spec and blueprint.has_attribute(target):
                    blueprint.set_attribute(target, str(spec[source]))
            transform = self.carla.Transform(
                self.carla.Location(x=float(spec.get("x", 0)), y=float(spec.get("y", 0)),
                                    z=float(spec.get("z", 0))),
                self.carla.Rotation(pitch=float(spec.get("pitch", 0)),
                                    yaw=float(spec.get("yaw", 0)),
                                    roll=float(spec.get("roll", 0))))
            sensor = self.world.spawn_actor(blueprint, transform, attach_to=self.ego)
            self.interface.register_sensor(tag, sensor_type, sensor)

            def callback(data, sensor_tag=tag, type_id=sensor_type):
                if type_id.startswith("sensor.camera"):
                    value = np.frombuffer(data.raw_data, dtype=np.uint8).copy().reshape(
                        (data.height, data.width, 4))
                elif type_id == "sensor.other.gnss":
                    value = np.array([data.latitude, data.longitude, data.altitude], dtype=np.float64)
                elif type_id == "sensor.other.imu":
                    value = np.array([data.accelerometer.x, data.accelerometer.y,
                                      data.accelerometer.z, data.gyroscope.x,
                                      data.gyroscope.y, data.gyroscope.z,
                                      data.compass], dtype=np.float64)
                else:
                    value = data
                self.interface.update_sensor(sensor_tag, value, data.frame)

            sensor.listen(callback)
            self.sensors.append(sensor)

    def add_speed(self, frame: int) -> None:
        if not self.has_speedometer:
            return
        transform, velocity = self.ego.get_transform(), self.ego.get_velocity()
        forward = transform.get_forward_vector()
        speed = velocity.x*forward.x + velocity.y*forward.y + velocity.z*forward.z
        import numpy as np
        self.interface.update_sensor("SPEED", {"speed": np.float64(speed)}, frame)

    def warmup(self, count: int = 10) -> None:
        for _ in range(count):
            frame = self.world.tick()
            self.add_speed(frame)
            self.interface.get_data(frame)

    def destroy(self) -> None:
        for sensor in self.sensors:
            try:
                sensor.stop()
                sensor.destroy()
            except RuntimeError:
                pass
        self.sensors.clear()


class NativeScenarioExecutor:
    def __init__(self, host: str = "127.0.0.1", port: int = 2000,
                 timeout: float = 300.0) -> None:
        self.host, self.port, self.timeout = host, port, timeout

    def run(self, scenario_path: Path, agent_path: Path, agent_config: str,
            output: Path) -> dict[str, Any]:
        spec = scenario_from_dict(json.loads(scenario_path.read_text(encoding="utf-8")))
        adapter = CarlaAdapter(self.host, self.port, self.timeout)
        carla = adapter._module()
        client = carla.Client(self.host, self.port)
        client.set_timeout(self.timeout)
        world = client.get_world()
        if spec.generated_map:
            xodr = build_opendrive(spec.generated_map)
            map_output = output.parent / f"{spec.scenario_id}.xodr"
            map_output.parent.mkdir(parents=True, exist_ok=True)
            map_output.write_text(xodr, encoding="utf-8")
            world = client.generate_opendrive_world(xodr, carla.OpendriveGenerationParameters(
                vertex_distance=2.0, max_road_length=500.0, wall_height=1.0,
                additional_width=0.6, smooth_junctions=True,
                enable_mesh_visibility=True, enable_pedestrian_navigation=False))
        elif spec.map_name.lower() not in world.get_map().name.lower():
            world = client.load_world(spec.map_name)
        original = world.get_settings()
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = 0.05
        world.apply_settings(settings)
        actors: list[Any] = []
        agent = None
        rig = None
        collision = {"hit": False}
        trace: list[dict[str, Any]] = []
        min_distance, min_ttc = math.inf, None
        control_runtime = EvaluationControl()
        try:
            world.set_weather(carla.WeatherParameters(
                cloudiness=spec.environment.cloudiness,
                precipitation=spec.environment.precipitation,
                fog_density=spec.environment.fog_density,
                sun_altitude_angle=spec.environment.sun_altitude_angle))
            ego = adapter._spawn(world, spec.ego, world.get_map().get_spawn_points())
            actors.append(ego)
            self._focus_spectator(carla, world, ego)
            world.tick()
            adversaries = [adapter._spawn_interaction_actor(
                carla, world, ego, actor, spec.family, index)
                for index, actor in enumerate(spec.adversaries)]
            actors.extend(adversaries)
            if spec.generated_map and spec.generated_map.realistic_environment:
                scenery = adapter._spawn_environment(carla, world, ego, spec)
                actors.extend(scenery)
            hazards = []
            for asset in spec.generated_assets:
                created = adapter._spawn_generated_asset(carla, world, ego, asset)
                hazards.extend(created)
                actors.extend(created)

            collision_bp = world.get_blueprint_library().find("sensor.other.collision")
            collision_sensor = world.spawn_actor(collision_bp, carla.Transform(), attach_to=ego)
            collision_sensor.listen(lambda _: collision.__setitem__("hit", True))
            actors.append(collision_sensor)

            module_spec = importlib.util.spec_from_file_location("carla_safety_uniad_target", agent_path)
            if module_spec is None or module_spec.loader is None:
                raise RuntimeError(f"Cannot load target adapter: {agent_path}")
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            agent_class = getattr(module, module.get_entry_point())
            agent = agent_class(self.host, self.port, False)
            gps_plan, world_plan = self._global_plan(world, ego)
            agent.set_global_plan(gps_plan, world_plan)
            agent.setup(agent_config)
            rig = NativeSensorRig(carla, world, ego, agent.sensor_interface)
            rig.setup(agent.sensors())
            rig.warmup()
            self._focus_spectator(carla, world, ego)
            world.tick()
            print(f"Native executor started scenario {spec.scenario_id}", flush=True)

            triggered: set[int] = set()
            steps = max(1, int(spec.oracle.max_duration_s / settings.fixed_delta_seconds))
            for step in range(steps):
                frame = world.tick(self.timeout)
                rig.add_speed(frame)
                sensor_data = agent.sensor_interface.get_data(frame)
                elapsed = (step + 1) * settings.fixed_delta_seconds
                control = agent.run_step(sensor_data, elapsed)
                control.manual_gear_shift = False
                ego.apply_control(control)
                control_runtime.on_frame(world)
                ego_state = adapter._state(ego)
                for index, (other, other_spec) in enumerate(zip(adversaries, spec.adversaries)):
                    other_state = adapter._state(other)
                    separation, current_ttc = distance(ego_state, other_state), ttc(ego_state, other_state)
                    min_distance = min(min_distance, separation)
                    if current_ttc is not None:
                        min_ttc = current_ttc if min_ttc is None else min(min_ttc, current_ttc)
                    if index not in triggered and separation <= (other_spec.trigger_distance_m or 0):
                        adapter._trigger(carla, other, other_spec)
                        triggered.add(index)
                    trace.append({"frame": frame, "time_s": elapsed,
                                  "actor_id": other.id, "distance_m": separation,
                                  "ttc_s": current_ttc})
                for hazard in hazards:
                    hazard_state = adapter._state(hazard)
                    separation, current_ttc = distance(ego_state, hazard_state), ttc(ego_state, hazard_state)
                    min_distance = min(min_distance, separation)
                    if current_ttc is not None:
                        min_ttc = current_ttc if min_ttc is None else min(min_ttc, current_ttc)
                    trace.append({"frame": frame, "time_s": elapsed,
                                  "actor_id": hazard.id, "distance_m": separation,
                                  "ttc_s": current_ttc, "generated_asset": True})
                if collision["hit"]:
                    break
            elapsed = min(steps, step + 1) * settings.fixed_delta_seconds
            if math.isinf(min_distance):
                min_distance = 1e6
            result = evaluate(spec.scenario_id, spec.oracle, collision["hit"], min_ttc,
                              min_distance, elapsed)
            output.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schema_version": "carla-safety-evaluation/0.1",
                       "scenario": spec.to_dict(), "result": result.to_dict(), "trace": trace}
            output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps(result.to_dict()), flush=True)
            self._focus_spectator(carla, world, ego)
            world.tick()
            preview_hold = max(0.0, float(os.environ.get("CSA_RESULT_PREVIEW_SECONDS", "60")))
            if preview_hold:
                print(f"Keeping finished scene visible for {preview_hold:g} seconds", flush=True)
                time.sleep(preview_hold)
            return payload
        finally:
            if rig:
                rig.destroy()
            if agent:
                try:
                    agent.destroy()
                except Exception:
                    pass
            actor_ids = [actor.id for actor in actors if getattr(actor, "is_alive", False)]
            for actor in actors:
                if getattr(actor, "type_id", "").startswith("sensor."):
                    try:
                        actor.stop()
                    except RuntimeError:
                        pass
            if actor_ids:
                client.apply_batch([carla.command.DestroyActor(actor_id) for actor_id in actor_ids])
            world.apply_settings(original)

    @staticmethod
    def _focus_spectator(carla: Any, world: Any, ego: Any) -> None:
        """Place the free spectator behind the ego without attaching or locking it."""
        transform = ego.get_transform()
        forward = transform.get_forward_vector()
        location = carla.Location(x=transform.location.x-forward.x*9.0,
                                  y=transform.location.y-forward.y*9.0,
                                  z=transform.location.z+4.5)
        rotation = carla.Rotation(pitch=-16.0, yaw=transform.rotation.yaw)
        world.get_spectator().set_transform(carla.Transform(location, rotation))

    @staticmethod
    def _global_plan(world: Any, ego: Any) -> tuple[list[Any], list[Any]]:
        start = world.get_map().get_waypoint(ego.get_location(), project_to_road=True)
        waypoints = [start]
        current = start
        for _ in range(80):
            choices = current.next(2.5)
            if not choices:
                break
            current = choices[0]
            waypoints.append(current)
        world_plan, gps_plan = [], []
        for waypoint in waypoints:
            transform = waypoint.transform
            geo = world.get_map().transform_to_geolocation(transform.location)
            command = RoadOption.LANEFOLLOW
            world_plan.append((transform, command))
            gps_plan.append(({"lat": geo.latitude, "lon": geo.longitude,
                              "z": geo.altitude}, command))
        return gps_plan, world_plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--agent-config", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=2000)
    args = parser.parse_args()
    NativeScenarioExecutor(port=args.port).run(
        args.scenario, args.agent, args.agent_config, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
