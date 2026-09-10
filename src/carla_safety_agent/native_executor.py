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
from .scenario_archive import read_verified_scenario
from .metrics import distance, evaluate, ttc
from .opendrive import build_opendrive
from .runtime_cleanup import Cleanup, cleanup_native_runtime
from agents.navigation.local_planner import RoadOption


class NativeSensorRig:
    def __init__(self, carla: Any, world: Any, ego: Any, interface: Any, client=None, journal=None) -> None:
        from carla_safety_agent.owned_resources import OwnedActors
        self.carla, self.world, self.ego, self.interface = carla, world, ego, interface
        self.client = client
        self.sensors: list[Any] = OwnedActors(journal)
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
            self.sensors.append(sensor)  # Own it even if registration/listen fails.
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
        from carla_safety_agent.owned_sensors import destroy_owned_sensors
        cleanup = Cleanup()
        for sensor in self.sensors:
            cleanup.attempt(f'Sensor {sensor.id} stop', sensor.stop)
        remaining, errors = destroy_owned_sensors(self.sensors, client=self.client, carla=self.carla)
        cleanup.errors.extend(errors)
        self.sensors = remaining
        cleanup.finish()


class NativeScenarioExecutor:
    def __init__(self, host: str = "127.0.0.1", port: int = 2000,
                 timeout: float = 300.0) -> None:
        self.host, self.port, self.timeout = host, port, timeout

    def run(self, scenario_path: Path, agent_path: Path, agent_config: str,
            output: Path) -> dict[str, Any]:
        document, scenario_digest = read_verified_scenario(scenario_path, os.environ.get('CSA_SCENARIO_SHA256'))
        from .execution_progress import progress_from_environment
        progress=progress_from_environment()
        def stage(phase,**fields):
            if progress:progress.emit(phase,**fields)
        stage('connecting')
        spec = scenario_from_dict(document)
        adapter = CarlaAdapter(self.host, self.port, self.timeout)
        carla = adapter._module()
        client = carla.Client(self.host, self.port)
        client.set_timeout(self.timeout)
        world = client.get_world()
        from .world_readiness import map_matches, require_idle_native_world
        require_idle_native_world(world)
        if spec.generated_map:
            stage('loading_world')
            xodr = build_opendrive(spec.generated_map)
            map_output = output.parent / f"{spec.scenario_id}.xodr"
            map_output.parent.mkdir(parents=True, exist_ok=True)
            map_output.write_text(xodr, encoding="utf-8")
            world = client.generate_opendrive_world(xodr, carla.OpendriveGenerationParameters(
                vertex_distance=2.0, max_road_length=500.0, wall_height=1.0,
                additional_width=0.6, smooth_junctions=True,
                enable_mesh_visibility=True, enable_pedestrian_navigation=False))
        elif not map_matches(spec.map_name, world.get_map().name):
            stage('loading_world')
            world = client.load_world(spec.map_name)
            if not map_matches(spec.map_name, world.get_map().name):
                raise RuntimeError('Loaded world does not match the requested map')
        original = world.get_settings()
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = 0.05
        from .owned_resources import OwnedActors, journal_from_environment
        journal = journal_from_environment(world)
        actors: list[Any] = OwnedActors(journal)
        agent = None
        rig = None
        capture = None
        collision = {"hit": False}
        trace: list[dict[str, Any]] = []
        min_distance, min_ttc = math.inf, None
        control_runtime = EvaluationControl()
        try:
            stage('spawning')
            world.apply_settings(settings)
            world.set_weather(carla.WeatherParameters(
                cloudiness=spec.environment.cloudiness,
                precipitation=spec.environment.precipitation,
                fog_density=spec.environment.fog_density,
                sun_altitude_angle=spec.environment.sun_altitude_angle))
            ego = adapter._spawn(world, spec.ego, world.get_map().get_spawn_points(), actors)
            self._focus_spectator(carla, world, ego)
            world.tick()
            adversaries = []
            for index, actor in enumerate(spec.adversaries):
                spawned = adapter._spawn_interaction_actor(carla, world, ego, actor, spec.family, index, actors)
                adversaries.append(spawned)
            if spec.generated_map and spec.generated_map.realistic_environment:
                adapter._spawn_environment(carla, world, ego, spec, actors)
            hazards = []
            for asset in spec.generated_assets:
                created = adapter._spawn_generated_asset(carla, world, ego, asset, actors)
                hazards.extend(created)

            collision_bp = world.get_blueprint_library().find("sensor.other.collision")
            collision_sensor = world.spawn_actor(collision_bp, carla.Transform(), attach_to=ego)
            actors.append(collision_sensor)
            collision_sensor.listen(lambda _: collision.__setitem__("hit", True))

            stage('loading_model')
            module_spec = importlib.util.spec_from_file_location("carla_safety_uniad_target", agent_path)
            if module_spec is None or module_spec.loader is None:
                raise RuntimeError(f"Cannot load target adapter: {agent_path}")
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            agent_class = getattr(module, module.get_entry_point())
            if os.environ.get('E2E_EXECUTION_MODE') == 'scenario':
                from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
                CarlaDataProvider.set_client(client)
                CarlaDataProvider.set_world(world)
            agent = agent_class(self.host, self.port, False)
            gps_plan, world_plan = self._global_plan(world, ego)
            agent.set_global_plan(gps_plan, world_plan)
            agent.setup(agent_config)
            stage('warming_sensors')
            from .sensor_schedule import synchronous_specs
            sensor_specs = synchronous_specs(agent.sensors(), settings.fixed_delta_seconds)
            rig = NativeSensorRig(carla, world, ego, agent.sensor_interface, client=client, journal=journal)
            rig.setup(sensor_specs)
            if os.environ.get('CSA_SENSOR_CAPTURE') == '1':
                from .sensor_capture import SensorCapture
                capture = SensorCapture(world, ego, sensor_specs, os.environ['CSA_EVALUATION_CONTROL_DIR'], scenario=spec.to_dict(), client=client, journal=journal)
            from .planning_observation import PlanningObservation
            planning_observation=PlanningObservation(agent) if capture else None
            rig.warmup()
            self._focus_spectator(carla, world, ego)
            world.tick()
            print(f"Native executor started scenario {spec.scenario_id}", flush=True)

            triggered: set[int] = set()
            steps = max(1, int(spec.oracle.max_duration_s / settings.fixed_delta_seconds))
            stage('inference',completed_steps=0,total_steps=steps)
            for step in range(steps):
                frame = world.tick(self.timeout)
                rig.add_speed(frame)
                sensor_data = agent.sensor_interface.get_data(frame)
                elapsed = (step + 1) * settings.fixed_delta_seconds
                exact_input = {k: (v[0], v[1].copy() if hasattr(v[1], 'copy') else v[1]) for k, v in sensor_data.items()} if capture else None
                control = (planning_observation.run_step(sensor_data,elapsed,frame=frame,
                           timestamp=world.get_snapshot().timestamp.elapsed_seconds,
                           ego_matrix=ego.get_transform().get_matrix()) if capture
                           else agent.run_step(sensor_data, elapsed))
                if capture:
                    try:
                        capture.process(exact_input, agent, control,planning=planning_observation.snapshot())
                    except Exception as exc:
                        print(f'Recording failed, model remains running: {exc}', flush=True)
                        capture.error = str(exc)
                        capture.close()
                        capture = None
                self._publish_telemetry(sensor_data, agent, control, frame, elapsed)
                control.manual_gear_shift = False
                ego.apply_control(control)
                control_runtime.on_frame(world)
                stage('inference',completed_steps=step+1,total_steps=steps)
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
                       "scenario_sha256": scenario_digest,
                       "execution_id": os.environ.get('CSA_EXECUTION_ID'),
                       "scenario": spec.to_dict(), "result": result.to_dict(), "trace": trace}
            output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps(result.to_dict()), flush=True)
            self._focus_spectator(carla, world, ego)
            world.tick()
            preview_hold = max(0.0, float(os.environ.get("CSA_RESULT_PREVIEW_SECONDS", "60")))
            if preview_hold:
                print(f"Keeping finished scene visible for {preview_hold:g} seconds", flush=True)
                stage('preview',completed_steps=step+1,total_steps=steps,preview_seconds=preview_hold)
                time.sleep(preview_hold)
            return payload
        finally:
            stage('cleaning')
            cleanup_native_runtime(carla, client, world, original, actors, capture, rig, agent)
            stage('worker_finished')

    @staticmethod
    def _publish_telemetry(sensor_data: dict[str, Any], agent: Any, control: Any,
                           frame: int, elapsed: float) -> None:
        """Publish synchronized model evidence for the local evaluation UI."""
        import numpy as np
        from PIL import Image

        root = Path(os.environ.get("CSA_EVALUATION_CONTROL_DIR", ".runtime/evaluation-control")) / "telemetry"
        root.mkdir(parents=True, exist_ok=True)
        camera_ids = ["CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT",
                      "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"]
        for camera_id in camera_ids:
            image = sensor_data.get(camera_id, (None, None))[1]
            if image is None:
                continue
            target = root / f"{camera_id}.jpg"
            temporary = target.with_suffix(".tmp.jpg")
            Image.fromarray(np.asarray(image)[:, :, :3][:, :, ::-1]).save(
                temporary, format="JPEG", quality=72)
            temporary.replace(target)
        speed = sensor_data.get("SPEED", (None, {"speed": 0.0}))[1]["speed"]
        gps = sensor_data.get("GPS", (None, []))[1]
        imu = sensor_data.get("IMU", (None, []))[1]
        metadata = getattr(agent, "pid_metadata", {}) or {}
        payload = {
            "frame": frame, "elapsed_s": elapsed,
            "inputs": {"camera_ids": camera_ids, "speed_mps": float(speed),
                       "gps": np.asarray(gps).tolist(), "imu": np.asarray(imu).tolist(),
                       "synchronized": len({value[0] for value in sensor_data.values()}) == 1},
            "outputs": {"steer": float(control.steer), "throttle": float(control.throttle),
                        "brake": float(control.brake), "plan": metadata.get("plan", []),
                        "target_speed": metadata.get("target_speed")},
        }
        temporary = root / "latest.tmp"
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(root / "latest.json")

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
    try:
        NativeScenarioExecutor(port=args.port).run(
            args.scenario, args.agent, args.agent_config, args.output)
    except KeyboardInterrupt:
        print('Native executor interrupted by stop request', flush=True)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
