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
import signal
import subprocess
import uuid
import mimetypes
import shutil
from functools import wraps
from dataclasses import replace
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import carla
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from carla_safety_agent.carla_adapter import CarlaAdapter
from carla_safety_agent.benchmark_catalog import algorithm_catalog, benchmark_report, route_catalog
from carla_safety_agent.blender_pipeline import BlenderPipeline
from carla_safety_agent.dataset import list_datasets
from carla_safety_agent.provenance import ActorProvenance
from carla_safety_agent.uv_audit import audit_uv
from carla_safety_agent.replay import replay_index, replay_file, replay_projection, replay_trajectory
from carla_safety_agent.natural_language import NaturalLanguageCompiler
from carla_safety_agent.session import SessionJournal
from carla_safety_agent.scene_store import SceneStore, validate_scene
from carla_safety_agent.material_library import MaterialLibrary, MaterialTransaction, exact_environment_target
from carla_safety_agent.visibility import VisibilityStore, VisibilityTransaction


HOST = "127.0.0.1"
PORT = int(os.environ.get("BRIDGE_PORT", "8765"))
CARLA_PORT = int(os.environ.get("CARLA_PORT", "2000"))
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
RUNTIME_MODE = "docker" if Path("/.dockerenv").exists() else "native"
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
_editor_actors = set()
_generated_actor_assets = {}
_thumbnail_cache = {}
_thumbnail_lock = threading.Lock()
_e2e_lock = threading.RLock()  # Start may initialize collection through evaluation_active().
_simulation_lock = threading.RLock()
_carla_client = None


def simulation_operation(function):
    """Drain editor RPC operations before handing the world to an evaluator."""
    @wraps(function)
    def guarded(*args, **kwargs):
        with _simulation_lock:
            return function(*args, **kwargs)
    return guarded

_e2e_process = None
_e2e_job = {"state": "idle", "kind": None, "started_at": None,
            "ended_at": None, "returncode": None, "command": None}
_scene_snapshot = None
_world_episode = None
_provenance = ActorProvenance(PROJECT_ROOT / '.runtime/actor-provenance.json')
_uv_audit = audit_uv(PROJECT_ROOT / 'tools/livery-designer/public')
_e2e_log = PROJECT_ROOT / ".runtime" / "uniad-ui.log"
_e2e_pid = PROJECT_ROOT / ".runtime" / "uniad.pid"
_evaluation_control_dir = PROJECT_ROOT / ".runtime" / "evaluation-control"
E2E_ROOT = Path(os.environ.get("E2E_ROOT", "/home/moresweet/Data/e2e"))
BENCH2DRIVE_ROOT = Path(os.environ.get("BENCH2DRIVE_ROOT", str(E2E_ROOT / "Bench2Drive")))
BENCH2DRIVE_ZOO = Path(os.environ.get("BENCH2DRIVE_ZOO", str(E2E_ROOT / "Bench2DriveZoo")))
BENCH2DRIVE_TCP_ZOO = Path(os.environ.get(
    "BENCH2DRIVE_TCP_ZOO", str(E2E_ROOT / "Bench2DriveZoo-tcp-admlp")))
DATASET_ROOT = Path(os.environ.get(
    "CSA_DATASET_ROOT", str(PROJECT_ROOT / ".runtime" / "generated-scenarios")))
UNIAD_PYTHON = Path(os.environ.get(
    "UNIAD_PYTHON", str(E2E_ROOT / "miniconda3/envs/uniad-cu128/bin/python")))
BLENDER = BlenderPipeline(PROJECT_ROOT)
SESSION = SessionJournal(PROJECT_ROOT / 'data')
SCENES = SceneStore(PROJECT_ROOT / 'data/scenes')
VISIBILITY = VisibilityStore(PROJECT_ROOT / 'data')
MATERIALS = MaterialLibrary(PROJECT_ROOT / 'data')
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


def e2e_routes() -> list[dict]:
    route_root = PROJECT_ROOT / ".runtime/generated-scenarios"
    paths = sorted(route_root.glob("*.json")) if route_root.is_dir() else []
    routes = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not all(key in payload for key in ("scenario_id", "ego", "oracle")):
                continue
        except (OSError, json.JSONDecodeError):
            continue
        routes.append({"name": payload["scenario_id"], "path": str(path), "count": 1,
                       "relative": f"{payload['scenario_id']} · {payload.get('family', 'scenario')}"})
    return routes


def evaluation_active() -> bool:
    with _e2e_lock:
        active = _e2e_job["state"] in ("running", "stopping")
    if active:
        return True
    if SESSION.snapshot()['state'] in ('preparing', 'running', 'stopping', 'recovering'):
        return True
    try:
        pid = int(_e2e_pid.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def evaluation_ready() -> bool:
    if not evaluation_active():
        return False
    state = _evaluation_control_dir / "state.json"
    try:
        fresh = time.time() - state.stat().st_mtime < 3.0
    except OSError:
        fresh = False
    return fresh


def evaluation_snapshot() -> dict | None:
    path = _evaluation_control_dir / "state.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def evaluation_command(action: str, payload: dict, timeout: float = 30.0) -> dict:
    if not evaluation_active():
        raise RuntimeError("No closed-loop evaluation is running")
    if not evaluation_ready():
        raise RuntimeError("Closed-loop evaluation is still initializing; try again shortly")
    commands = _evaluation_control_dir / "commands"
    results = _evaluation_control_dir / "results"
    commands.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    command_id = uuid.uuid4().hex
    target = commands / f"{command_id}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"action": action, "payload": payload}), encoding="utf-8")
    temporary.replace(target)
    result_path = results / target.name
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result_path.unlink(missing_ok=True)
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Evaluation edit failed"))
            return result
        except FileNotFoundError:
            time.sleep(0.05)
        except json.JSONDecodeError:
            time.sleep(0.02)
    target.unlink(missing_ok=True)
    raise RuntimeError("The evaluator did not apply the edit within 30 seconds")


def _benchmark_result_failed(results_path: Path) -> bool:
    if not results_path.is_file():
        return True
    try:
        payload = json.loads(results_path.read_text())
    except (OSError, json.JSONDecodeError):
        return True
    checkpoint = payload.get("_checkpoint", {})
    records = checkpoint.get("records", [])
    global_status = checkpoint.get("global_record", {}).get("status")
    return global_status == "Failed" or any(
        str(record.get("status", "")).lower().startswith("failed")
        for record in records
    )


def _finish_e2e(process):
    returncode = process.wait()
    cleanup_error = None
    if _e2e_process is process:
        try:
            SESSION.transition('recovering')
        except OSError as exc:
            # Journal storage failure must not prevent restoring the simulator.
            cleanup_error = f'Session journal: {exc}'
    if _e2e_process is process and _e2e_job.get("kind") in ("run", "preset-run", "sensor-rig"):
        try:
            restore_editor_world()
        except Exception as exc:
            cleanup_error = str(exc)
    try:
        if _e2e_pid.read_text().strip() == str(process.pid):
            _e2e_pid.unlink(missing_ok=True)
    except OSError:
        pass
    with _e2e_lock:
        if _e2e_process is process:
            results_path = Path(_e2e_job.get("results") or "")
            benchmark_failed = bool(_e2e_job.get("results")) and returncode == 0 and _benchmark_result_failed(results_path)
            state = ("failed" if _e2e_job.get('startup_error') else "stopped" if _e2e_job["state"] == "stopping" else
                     "succeeded" if returncode == 0 and not benchmark_failed else "failed")
            _e2e_job.update(state="failed" if cleanup_error else state, cleanup_error=cleanup_error,
                            ended_at=time.time(), returncode=returncode)
            SESSION.transition('recovering' if cleanup_error else 'failed' if state == 'failed' else
                               'stopped' if state == 'stopped' else 'completed',
                               returncode=returncode, error=cleanup_error or _e2e_job.get('startup_error'),
                               outcome={'execution': state, 'benchmark_failed': benchmark_failed,
                                        'failure_category': 'world_recovery' if cleanup_error else
                                            'startup' if _e2e_job.get('startup_error') else
                                            'process_exit' if returncode not in (0, 130) and state != 'stopped' else
                                            'benchmark_result' if benchmark_failed and state != 'stopped' else None})


def _abort_e2e_start(process, error):
    """Retain ownership until a freshly spawned child actually exits and recovers."""
    _e2e_job.update(state='running', startup_error=str(error))
    try:
        if process.poll() is None:
            # This Popen is the child just created in this request, not a saved PID.
            os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        pass
    finally:
        # Even failed signalling must retain a waiter; never declare a live child failed/idle.
        threading.Thread(target=_finish_e2e, args=(process,), daemon=True).start()


def collection_request(data):
    if data.get('recording') and not evaluation_active():
        raise RuntimeError('请先启动独立采集或闭环测试')
    payload = {'id': uuid.uuid4().hex, 'recording': bool(data.get('recording')),
               'every': max(1, min(100, int(data.get('every', 5)))),
               'max_frames': max(1, min(10000, int(data.get('max_frames', 2000))))}
    target = _evaluation_control_dir/'collection-request.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(payload))
    temp.replace(target)
    return {'ok': True, 'request': payload}


def e2e_status() -> dict:
    with _e2e_lock:
        job = dict(_e2e_job)
    if job["state"] == "idle" and evaluation_active():
        job.update(state="running", kind="recovered-evaluation")
    log = ""
    if _e2e_log.is_file():
        with _e2e_log.open("rb") as stream:
            stream.seek(max(0, _e2e_log.stat().st_size - 24000))
            log = stream.read().decode("utf-8", errors="replace")
    results_path = Path(job.get("results") or PROJECT_ROOT / "runs/uniad/latest.json")
    results = None
    if results_path.is_file():
        try:
            results = json.loads(results_path.read_text())
        except (OSError, json.JSONDecodeError):
            results = {"error": "Result file is not valid JSON"}
    algorithms = algorithm_catalog(BENCH2DRIVE_ZOO, BENCH2DRIVE_TCP_ZOO)
    for item in algorithms:
        item.update(framework="Native Scenario Executor",
                    enabled=item["status"] == "available")
    return {"ok": True, "algorithms": algorithms, "job": job, 'session': SESSION.snapshot(),
            "routes": e2e_routes(), "log": log, "results": results}


@simulation_operation
def start_e2e(data: dict) -> dict:
    global _e2e_process
    action = str(data.get("action", "doctor"))
    if action not in ("doctor", "model-smoke", "run", "preset-run", "sensor-rig"):
        raise RuntimeError(f"Unknown UniAD action: {action}")
    if action != 'sensor-rig' and not UNIAD_PYTHON.is_file():
        raise RuntimeError(f"UniAD environment is missing: {UNIAD_PYTHON}")
    if evaluation_active():
        raise RuntimeError("An evaluation is already running or stopping")
    if action in ("run", "preset-run", "sensor-rig"):
        if shutil.disk_usage(PROJECT_ROOT).free < 1024**3:
            raise RuntimeError('At least 1 GiB free disk space is required before evaluation')
        # Fail promptly instead of launching a model against a crashed server.
        settings = connect_world().get_settings()
        if action == 'sensor-rig' and settings.synchronous_mode:
            raise RuntimeError('Another synchronous owner is active')
    if action in ("run", "model-smoke") and data.get("algorithm", "uniad-tiny") != "uniad-tiny":
        raise RuntimeError("This action supports UniAD-Tiny only; use preset closed-loop testing for other models")
    with _e2e_lock:
        if _e2e_process is not None and _e2e_process.poll() is None:
            raise RuntimeError("A UniAD task is already running")
        if action == "doctor":
            command = [str(UNIAD_PYTHON), str(PROJECT_ROOT / "integration/uniad/doctor.py"),
                       "--root", str(E2E_ROOT), "--carla-port", str(CARLA_PORT)]
        elif action == "model-smoke":
            command = [str(UNIAD_PYTHON), str(PROJECT_ROOT / "integration/uniad/model_smoke.py")]
        elif action == "run":
            route = Path(str(data.get("route", ""))).resolve()
            allowed = {Path(item["path"]).resolve() for item in e2e_routes()}
            if route not in allowed:
                raise RuntimeError("Select a generated ScenarioSpec from the local catalog")
            command = [str(PROJECT_ROOT / "scripts/run_uniad_target.sh")]
        elif action == 'sensor-rig':
            mode, frames = str(data.get('mode','stationary')), data.get('frames',200)
            if mode not in ('stationary','autopilot','manual') or isinstance(frames,bool) or not isinstance(frames,int) or not 10 <= frames <= 100000:
                raise ValueError('Select stationary/autopilot/manual and 10..100000 frames')
            if not isinstance(data.get('recording',True), bool): raise ValueError('recording must be boolean')
            for key, default, upper in (('every',1,100), ('max_frames',2000,10000)):
                value = data.get(key,default)
                if isinstance(value,bool) or not isinstance(value,int) or not 1 <= value <= upper:
                    raise ValueError(f'{key} must be an integer from 1 to {upper}')
            command = [sys.executable,str(PROJECT_ROOT/'tools/run_sensor_rig.py'),
                       '--port',str(CARLA_PORT),'--frames',str(frames),'--mode',mode]
        else:
            collection = Path(str(data.get("collection", ""))).resolve()
            route_id = str(data.get("route_id", ""))
            catalogs = route_catalog(BENCH2DRIVE_ROOT)["collections"]
            allowed = {Path(item["path"]).resolve(): {route["id"] for route in item["routes"]}
                       for item in catalogs}
            if collection not in allowed or route_id not in allowed[collection]:
                raise RuntimeError("Select a valid preset route from the external catalog")
            algorithm = str(data.get("algorithm", "uniad-tiny"))
            available = {item["id"] for item in
                         algorithm_catalog(BENCH2DRIVE_ZOO, BENCH2DRIVE_TCP_ZOO)
                         if item["status"] == "available"}
            if algorithm not in available:
                raise RuntimeError("The selected algorithm is not installed with a runnable checkpoint")
            route = collection
            command = [str(PROJECT_ROOT / "scripts/run_benchmark_preset.sh")]
        _e2e_log.parent.mkdir(parents=True, exist_ok=True)
        log_stream = _e2e_log.open("wb")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.update(E2E_ROOT=str(E2E_ROOT), UNIAD_PYTHON=str(UNIAD_PYTHON),
                   CSA_EVALUATION_CONTROL_DIR=str(_evaluation_control_dir),
                   CSA_SENSOR_CAPTURE="1", CSA_DATASET_ROOT=str(DATASET_ROOT))
        if action == 'sensor-rig':
            env['PYTHONPATH'] = os.pathsep.join((str(PROJECT_ROOT/'src'),os.environ.get('PYTHONPATH','')))
        if action in ("run", "preset-run", "sensor-rig"):
            _hero_lock.clear()
            collection_request({'recording': False})
            results_path = None if action == 'sensor-rig' else (PROJECT_ROOT / "runs/uniad" / f"{route.stem}.json"
                            if action == "run" else PROJECT_ROOT / "runs/benchmark" /
                            f"{algorithm}-{route.stem}-{route_id}-{uuid.uuid4().hex[:8]}.json")
            (_evaluation_control_dir / "state.json").unlink(missing_ok=True)
            (_evaluation_control_dir / 'sensor-rig-status.json').unlink(missing_ok=True)
            for directory in (_evaluation_control_dir / "commands",
                              _evaluation_control_dir / "results",
                              _evaluation_control_dir / "textures"):
                directory.mkdir(parents=True, exist_ok=True)
                for stale in directory.glob("*"):
                    if stale.is_file():
                        stale.unlink()
            telemetry_dir = _evaluation_control_dir / "telemetry"
            telemetry_dir.mkdir(parents=True, exist_ok=True)
            for stale in telemetry_dir.glob("*"):
                if stale.is_file():
                    stale.unlink()
        if action == "run":
            env["SCENARIO"] = str(route)
            env["RESULTS"] = str(results_path)
        elif action == "preset-run":
            env.update(ROUTES=str(route), ROUTE_ID=route_id, RESULTS=str(results_path),
                       ALGORITHM=algorithm,
                       BENCH2DRIVE_ROOT=str(BENCH2DRIVE_ROOT),
                       BENCH2DRIVE_ZOO=str(BENCH2DRIVE_ZOO),
                       BENCH2DRIVE_TCP_ZOO=str(BENCH2DRIVE_TCP_ZOO))
        execution_id = SESSION.begin(action, {'request': data, 'command': command,
                              'python': sys.executable if action == 'sensor-rig' else str(UNIAD_PYTHON), 'carla_port': CARLA_PORT,
                              'results': str(results_path) if action in ('run', 'preset-run') else None})
        env['CSA_EXECUTION_ID'] = execution_id
        _e2e_job.clear()
        _e2e_job.update(state="running", kind=action, started_at=time.time(),
                        ended_at=None, returncode=None, command=command,
                        algorithm=algorithm if action == "preset-run" else None if action == 'sensor-rig' else "uniad-tiny",
                        collection=str(route) if action == "preset-run" else None,
                        route_id=route_id if action == "preset-run" else None,
                        results=str(results_path) if action in ("run", "preset-run") else None)
        launched = None
        try:
            _e2e_process = subprocess.Popen(
                command, cwd=PROJECT_ROOT, env=env, stdout=log_stream,
                stderr=subprocess.STDOUT, start_new_session=True)
            launched = _e2e_process
            SESSION.attach(_e2e_process.pid)
            if action == 'sensor-rig':
                collection_request({'recording':data.get('recording',True),
                                    'every':data.get('every',1),'max_frames':data.get('max_frames',2000)})
            _e2e_pid.write_text(f"{_e2e_process.pid}\n")
        except Exception as exc:
            if launched is not None:
                _abort_e2e_start(launched, exc)
            else:
                _e2e_job.update(state='failed', startup_error=str(exc))
                SESSION.transition('failed', error=str(exc))
            raise
        finally:
            log_stream.close()
        threading.Thread(target=_finish_e2e, args=(_e2e_process,), daemon=True).start()
        return {"ok": True, "job": dict(_e2e_job)}


def stop_sensor_rig(data):
    with _e2e_lock:
        current = SESSION.snapshot()
        if current.get('kind') != 'sensor-rig' or current.get('run_id') != data.get('run_id'):
            raise ValueError('Capture session changed; refusing to stop another task')
        return stop_e2e()


def manual_sensor_control(data):
    from carla_safety_agent.manual_control import validate_control
    from carla_safety_agent.sensor_capture import atomic_json
    if not isinstance(data,dict) or 'control' not in data: raise ValueError('Control object required')
    with _e2e_lock:
        current=SESSION.snapshot()
        if (current.get('state')!='running' or current.get('kind')!='sensor-rig' or
            current.get('run_id')!=data.get('run_id') or
            current.get('configuration',{}).get('request',{}).get('mode')!='manual' or
            not SESSION.owned_pid()):
            raise ValueError('No matching live manual capture session')
        command={'execution_id':current['run_id'],'issued_monotonic':time.monotonic(),
                 'control':validate_control(data.get('control',{}))}
        atomic_json(_evaluation_control_dir/'manual-control.json',command)
        return {'ok':True,'run_id':current['run_id'],'expires_after_s':.5}


def stop_e2e() -> dict:
    with _e2e_lock:
        if _e2e_job["state"] == "stopping":
            return {"ok": True, "state": "stopping"}
        process = _e2e_process
        if process is not None and process.poll() is None:
            pid = process.pid
        else:
            try:
                pid = int(_e2e_pid.read_text().strip())
                os.kill(pid, 0)
            except (OSError, ValueError):
                return {"ok": True, "state": _e2e_job["state"]}
        # Let the evaluator run its finally blocks so synchronous mode and the
        # traffic manager are restored before the editor becomes interactive.
        if SESSION.owned_pid() != pid:
            raise RuntimeError('Cannot safely stop this PID: execution identity is not verified')
        os.killpg(pid, signal.SIGINT)
        SESSION.transition('stopping')
        _e2e_job["state"] = "stopping"
        return {"ok": True, "state": "stopping"}


def resume_session():
    """Recover only our persisted job; never signal an unverified legacy PID."""
    previous = SESSION.snapshot()
    if previous['state'] not in ('preparing', 'running', 'stopping', 'recovering'):
        return
    while SESSION.owned_pid():
        time.sleep(1)
    SESSION.reconcile()
    identity = previous.get('process')
    if identity:
        try:
            if _e2e_pid.read_text().strip() == str(identity['pid']):
                _e2e_pid.unlink()
        except OSError:
            pass
    try:
        if previous.get('kind') in ('run', 'preset-run', 'sensor-rig'):
            restore_editor_world()
        SESSION.transition('failed', error='Bridge restarted during execution; result requires review')
    except Exception as exc:
        # Keep recovering to block competing RPCs; explicit retry is available.
        SESSION.transition('recovering', error=str(exc))
    with _e2e_lock:
        _e2e_job.update(state='failed', ended_at=time.time())


@simulation_operation
def recover_session():
    if SESSION.owned_pid() or (_e2e_process is not None and _e2e_process.poll() is None):
        raise RuntimeError('Stop the live execution before recovering the world')
    current = SESSION.snapshot()
    if current['state'] == 'recovering':
        restore_editor_world()
        SESSION.transition('failed', error='World recovered; interrupted execution needs review')
    return {'ok': True, 'session': SESSION.snapshot()}


def system_preflight():
    """Read-only local checks; never connect a second client during evaluation."""
    checks = [{'id': 'model_environment', 'ok': UNIAD_PYTHON.is_file(), 'detail': str(UNIAD_PYTHON)},
              {'id': 'disk_space', 'ok': shutil.disk_usage(PROJECT_ROOT).free > 1024**3,
               'free_bytes': shutil.disk_usage(PROJECT_ROOT).free},
              {'id': 'session_idle', 'ok': not evaluation_active(), 'detail': SESSION.snapshot()['state']}]
    if not evaluation_active():
        try:
            world = connect_world()
            checks.append({'id': 'carla', 'ok': True, 'map': world.get_map().name,
                           'synchronous': world.get_settings().synchronous_mode})
        except Exception as exc:
            checks.append({'id': 'carla', 'ok': False, 'detail': str(exc)})
    return {'ok': True, 'ready': all(c['ok'] for c in checks), 'checks': checks,
            'session': SESSION.snapshot()}


@simulation_operation
def compile_scenario(data: dict, execute: bool = False) -> dict:
    if execute and evaluation_active():
        raise RuntimeError("Stop the closed-loop evaluation before running a generated scene")
    compilation = NaturalLanguageCompiler().compile(
        str(data.get("description", "")), int(data.get("seed", 7)))
    scenario = compilation.scenario
    if data.get("max_duration_s") is not None:
        duration = max(0.05, float(data["max_duration_s"]))
        scenario = replace(scenario, oracle=replace(scenario.oracle, max_duration_s=duration))
    response = {"ok": True, "scenario": scenario.to_dict(),
                "warnings": list(compilation.warnings),
                "extracted": compilation.extracted}
    catalog = PROJECT_ROOT / ".runtime" / "generated-scenarios"
    catalog.mkdir(parents=True, exist_ok=True)
    scenario_path = catalog / f"{scenario.scenario_id}.json"
    scenario_path.write_text(json.dumps(scenario.to_dict(), indent=2,
                                        ensure_ascii=False), encoding="utf-8")
    response["scenario_path"] = str(scenario_path)
    if execute:
        output = PROJECT_ROOT / ".runtime" / "generated-scenarios"
        result = CarlaAdapter(HOST, CARLA_PORT, 120.0).run(
            scenario, output, render=True)
        response["result"] = result.to_dict()
        response["output_dir"] = str(output)
        if result.trace_path:
            response["manifest_path"] = str(Path(result.trace_path).parent / "manifest.json")
    return response


def evaluate_scenario(data: dict) -> dict:
    """Compile a natural-language scene and launch it in the native executor."""
    response = compile_scenario(data)
    response["evaluation"] = start_e2e({
        "action": "run", "algorithm": "uniad-tiny", "route": response["scenario_path"]})
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
    global _carla_client, _world_episode
    with _simulation_lock:
        if evaluation_active():
            raise RuntimeError("Closed-loop evaluation owns CARLA; wait for it to stop")
        if _carla_client is None:
            _carla_client = carla.Client(HOST, CARLA_PORT)
            _carla_client.set_timeout(5.0)
        world = _carla_client.get_world()
        if _world_episode != world.id:
            _world_episode = world.id
            _editor_actors.clear()
            _environment_cache.clear()
            _actor_object_names.clear()
            _provenance.mark(world.id, [a for a in world.get_actors()
                if a.type_id.startswith(('vehicle.', 'walker.', 'static.prop.'))], 'existing', overwrite=False)
        return world


def _origin_for_actor(actor):
    return _provenance.origin(_world_episode, actor)


@simulation_operation
def scene_preview():
    """Render the actual spectator view; never substitute proxy geometry."""
    world = connect_world()
    ready = threading.Event()
    frames = []
    bp = world.get_blueprint_library().find('sensor.camera.rgb')
    bp.set_attribute('image_size_x', '960')
    bp.set_attribute('image_size_y', '540')
    sensor = world.spawn_actor(bp, world.get_spectator().get_transform())
    def receive(frame):
        if not ready.is_set():
            frames.append(bytes(frame.raw_data))
            ready.set()
    try:
        sensor.listen(receive)
        if not ready.wait(8):
            raise RuntimeError('CARLA 实景取景超时，请确认仿真正在推进')
        output = io.BytesIO()
        Image.frombytes('RGBA', (960, 540), frames[0], 'raw', 'BGRA').convert('RGB').save(output, 'JPEG', quality=90)
        return output.getvalue()
    finally:
        sensor.stop()
        sensor.destroy()


@simulation_operation
def restore_editor_world():
    """The evaluator has exited: also recover an interrupt during its setup."""
    global _carla_client
    if _carla_client is None:
        _carla_client = carla.Client(HOST, CARLA_PORT)
        _carla_client.set_timeout(5.0)
    world = _carla_client.get_world()
    settings = world.get_settings()
    if settings.synchronous_mode:
        settings.synchronous_mode = False
        settings.fixed_delta_seconds = None
        settings.spectator_as_ego = True
        world.apply_settings(settings)


@simulation_operation
def texture_targets(kind: str) -> dict:
    prefix = {"road": "Road_Road_", "building": "BP_House"}.get(kind, "")
    names = sorted(name for name in connect_world().get_names_of_all_objects()
                   if prefix and name.startswith(prefix))
    return {"ok": True, "kind": kind, "count": len(names), "objects": names}


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
    rotation = actor.get_transform().rotation
    return {"key": f"actor:{actor.id}", "id": actor.id, "kind": kind,
            "name": actor.type_id, "label": f"{actor.type_id} · #{actor.id}",
            "location": vector(actor.get_location()),
            "extent": vector(extent),
            "rotation": {"pitch": rotation.pitch, "yaw": rotation.yaw, "roll": rotation.roll},
            "origin": _origin_for_actor(actor),
            "hero": actor.attributes.get("role_name") == "hero"}


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
            "source": "environment", "category": category, "group": group,
            "origin": "existing",
            "kind": coarse, "name": obj.name,
            "label": f"{obj.name} · {str(obj.id)[-6:]}",
            "location": vector(location), "extent": vector(box.extent),
            "rotation": {"pitch": obj.transform.rotation.pitch,
                         "yaw": obj.transform.rotation.yaw,
                         "roll": obj.transform.rotation.roll}}


@simulation_operation
def catalog_categories() -> dict:
    if evaluation_active():
        snapshot = evaluation_snapshot() or {}
        actors = snapshot.get("objects", [])
        categories = [{"id": name, "group": group, "coarse": coarse,
                       "count": 0, "editable": "visibility_texture"}
                      for name, (_, group, coarse) in ENVIRONMENT_CATEGORIES.items()]
        for name, kind in (("vehicles", "vehicle"), ("pedestrians", "walker"),
                           ("spawned_props", "prop")):
            categories.append({"id": name, "group": "dynamic", "coarse": kind,
                               "count": sum(item.get("kind") == kind for item in actors),
                               "editable": "full"})
        return {"ok": True, "map": snapshot.get("map", "evaluation"),
                "categories": categories, "evaluation_active": True}
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


@simulation_operation
def catalog_objects(category: str, query: str, offset: int, limit: int, origin: str = "all") -> dict:
    if evaluation_active():
        if category in ENVIRONMENT_CATEGORIES:
            return evaluation_command("catalog_environment", {
                "category": category, "query": query, "offset": offset, "limit": limit, "origin": origin})
        snapshot = evaluation_snapshot() or {}
        kind = {"vehicles": "vehicle", "pedestrians": "walker",
                "spawned_props": "prop"}.get(category)
        if not kind:
            raise RuntimeError(f"Unknown category: {category}")
        records = [item for item in snapshot.get("objects", []) if item.get("kind") == kind]
        if origin != "all":
            records = [item for item in records if item.get('origin', 'existing') == origin]
        if query:
            needle = query.casefold()
            records = [item for item in records if needle in item["name"].casefold()
                       or needle in str(item["id"])]
        return {"ok": True, "category": category, "total": len(records),
                "offset": offset, "limit": limit, "objects": records[offset:offset+limit],
                "evaluation_active": True}
    world = connect_world()
    if category in ENVIRONMENT_CATEGORIES:
        hidden = {record['object_id'] for record in VISIBILITY.records(world.id)}
        records = [environment_record(obj, category)
                   for obj in environment_objects(world, category)]
        for record in records:
            record['visible'] = record['id'] not in hidden
            record['visibility_source'] = 'studio-managed'
    else:
        pattern = {"vehicles": "vehicle.*", "pedestrians": "walker.*",
                   "spawned_props": "static.prop.*"}.get(category)
        if not pattern:
            raise RuntimeError(f"Unknown category: {category}")
        records = [actor_record(actor) | {"source": "actor", "category": category,
                                             "group": "dynamic"}
                   for actor in world.get_actors().filter(pattern)]
    if origin != "all":
        records = [item for item in records if item.get('origin', 'existing') == origin]
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


@simulation_operation
def focus_environment(object_id: int) -> dict:
    if evaluation_active():
        return evaluation_command("focus_environment", {"object_id": object_id})
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


@simulation_operation
def set_environment_visibility(object_id: int, enabled: bool) -> dict:
    if not isinstance(enabled, bool): raise ValueError('Visibility must be boolean')
    if evaluation_active():
        return evaluation_command("environment_visibility", {
            "object_id": object_id, "visible": enabled})
    world = connect_world()
    category, obj = find_environment(world, object_id)
    world.enable_environment_objects({obj.id}, enabled)
    VISIBILITY.record(world.id, obj.id, obj.name, enabled)
    return {"ok": True, "id": str(obj.id), "category": category,
            "visible": enabled}


@simulation_operation
def spawn_object(blueprint_id: str, transform_data: dict) -> dict:
    if evaluation_active():
        return evaluation_command("spawn", {"blueprint_id": blueprint_id,
                                             "transform": transform_data})
    # Thumbnail staging also creates actors; do not mix its mesh names into this delta.
    with _thumbnail_lock:
        return _spawn_editor_object(blueprint_id, transform_data)


def _spawn_editor_object(blueprint_id: str, transform_data: dict) -> dict:
    world = connect_world()
    generated = BLENDER.registry().get(blueprint_id)
    runtime_blueprint_id = "static.prop.mesh" if generated else blueprint_id
    blueprint = world.get_blueprint_library().find(runtime_blueprint_id)
    if generated:
        blueprint.set_attribute("mesh_path", generated["mesh_path"])
        blueprint.set_attribute("mass", str(float(transform_data.get("mass", 0))))
        blueprint.set_attribute("scale", str(float(
            transform_data.get("scale", generated.get("default_scale", 100.0)))))
    if not generated and not blueprint_id.startswith(("vehicle.", "walker.", "static.prop.")):
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
                0.3 if blueprint_id.startswith("vehicle.") else
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
    # Editor placement is static until a scenario executor explicitly takes control.
    if blueprint_id.startswith("vehicle."):
        actor.set_autopilot(False)
        actor.set_simulate_physics(False)
        actor.set_target_velocity(carla.Vector3D())
        actor.set_target_angular_velocity(carla.Vector3D())
    _editor_actors.add(actor.id)
    _provenance.mark(world.id, [actor], 'user')
    stable_id = _provenance.records(world.id)[str(actor.id)]['stable_id']
    _provenance.bind(world.id, actor, stable_id, blueprint_id=blueprint_id,
                     spawn_options={k: transform_data[k] for k in ('mass', 'scale') if k in transform_data})
    if generated:
        _generated_actor_assets[actor.id] = blueprint_id
    after = set(world.get_names_of_all_objects())
    created_names = sorted(after-before)
    if len(created_names) == 1:
        _actor_object_names[actor.id] = created_names[0]
    return {"ok": True, "object": actor_record(actor)}


def transform_record(transform):
    return {'location': {k: float(getattr(transform.location, k)) for k in ('x','y','z')},
            'rotation': {k: float(getattr(transform.rotation, k)) for k in ('pitch','yaw','roll')}}


@simulation_operation
def save_scene(data):
    world = connect_world()
    provenance = _provenance.records(world.id)
    objects = []
    for actor in world.get_actors():
        record = provenance.get(str(actor.id), {})
        if record.get('origin') != 'user' or record.get('type_id') != actor.type_id:
            continue
        objects.append({'stable_id': record['stable_id'], 'origin': 'user',
                        'blueprint_id': record.get('blueprint_id', actor.type_id),
                        'transform': transform_record(actor.get_transform()),
                        'spawn_options': record.get('spawn_options', {})})
    weather = world.get_weather()
    weather_keys = ('cloudiness','precipitation','precipitation_deposits','wind_intensity',
                    'sun_azimuth_angle','sun_altitude_angle','fog_density','fog_distance','wetness')
    document = {'map': world.get_map().name, 'objects': objects,
                'environment_materials': list(MATERIALS.overrides(world.id).values()),
                'hidden_environment': VISIBILITY.records(world.id),
                'weather': {k: float(getattr(weather,k)) for k in weather_keys},
                'spectator': transform_record(world.get_spectator().get_transform()),
                'limitations': ['Managed user actors, exact environment material slots and studio-managed visibility; legacy actor textures and external visibility changes not captured']}
    return {'ok': True, **SCENES.save(document, data.get('name',''), data.get('scene_id'), data.get('expected_version'))}


@simulation_operation
def restore_scene(data):
    world = connect_world()
    saved = SCENES.read(str(data['scene_id']), data.get('version'))
    document = validate_scene(saved['document'])
    if world.get_map().name != document['map']:
        raise RuntimeError('Scene belongs to another map; explicit map handoff is not implemented yet')
    registry = BLENDER.registry()
    material_transaction = prepare_scene_materials(world, document)
    visibility_transaction = prepare_scene_visibility(world, document)
    for obj in document['objects']:
        blueprint = obj['blueprint_id']
        if blueprint not in registry:
            world.get_blueprint_library().find(blueprint)
    provenance = _provenance.records(world.id)
    live = {r.get('stable_id'): world.get_actor(int(actor_id)) for actor_id, r in provenance.items()
            if r.get('origin') == 'user'}
    created, moved = [], []
    previous_weather, previous_view = world.get_weather(), world.get_spectator().get_transform()
    # Validate native properties before the first spawn, move or material edit.
    weather = world.get_weather()
    for key, value in document.get('weather', {}).items():
        if not hasattr(weather, key): raise ValueError(f'Unsupported weather property: {key}')
        setattr(weather, key, value)
    view = document.get('spectator')
    restored_view = carla.Transform(carla.Location(**view['location']), carla.Rotation(**view['rotation'])) if view else None
    for obj in document['objects']:
        actor = live.get(obj['stable_id'])
        if actor is not None:
            old = provenance[str(actor.id)]
            if old.get('type_id') != actor.type_id or old.get('blueprint_id', actor.type_id) != obj['blueprint_id']:
                raise RuntimeError('Stable ID blueprint mismatch; refusing to update another object')
    try:
        for obj in document['objects']:
            actor = live.get(obj['stable_id'])
            if actor is not None:
                old = provenance[str(actor.id)]
                if old.get('blueprint_id', actor.type_id) != obj['blueprint_id']:
                    raise RuntimeError('Stable ID blueprint mismatch; refusing to update another object')
                moved.append((actor, actor.get_transform()))
                update_actor(actor.id, obj['transform'])
            else:
                result = spawn_object(obj['blueprint_id'], {**obj.get('spawn_options', {}), **obj['transform']})
                actor = world.get_actor(result['object']['id'])
                created.append(actor)
                _provenance.bind(world.id, actor, obj['stable_id'], blueprint_id=obj['blueprint_id'],
                                 spawn_options=obj.get('spawn_options', {}))
                live[obj['stable_id']] = actor
        world.set_weather(weather)
        if material_transaction:
            material_transaction.apply()
        if visibility_transaction:
            visibility_transaction.apply()
        if restored_view:
            world.get_spectator().set_transform(restored_view)
    except Exception as original:
        recovery_errors = []
        if visibility_transaction:
            try: visibility_transaction.rollback()
            except Exception as exc: recovery_errors.append(str(exc))
        if material_transaction:
            try: material_transaction.rollback()
            except Exception as exc: recovery_errors.append(str(exc))
        for actor, transform in reversed(moved):
            try: actor.set_transform(transform)
            except Exception as exc: recovery_errors.append(str(exc))
        for actor in created:
            try: delete_actor(actor.id)
            except Exception as exc: recovery_errors.append(str(exc))
        try: world.set_weather(previous_weather)
        except Exception as exc: recovery_errors.append(str(exc))
        try: world.get_spectator().set_transform(previous_view)
        except Exception as exc: recovery_errors.append(str(exc))
        if recovery_errors:
            raise RuntimeError(f'Scene restore failed: {original}; recovery incomplete: {recovery_errors}') from original
        raise
    return {'ok': True, **saved, 'restored': len(document['objects']), 'spawned': len(created),
            'bindings': {obj['stable_id']: live[obj['stable_id']].id for obj in document['objects']},
            'mode': 'merge', 'note': 'Unrelated actors preserved; managed environment materials and visibility restored; legacy actor textures not restored'}


def prepare_scene_visibility(world, document):
    if 'hidden_environment' not in document: return None
    def apply(record, visible):
        world.enable_environment_objects({int(record['object_id'])}, visible)
        VISIBILITY.record(world.id, record['object_id'], record['name'], visible)
    return VisibilityTransaction(VISIBILITY.records(world.id), document['hidden_environment'],
                                 lambda number: find_environment(world, number)[1].name, apply)


def prepare_scene_materials(world, document):
    if 'environment_materials' not in document:
        return None  # Older scenes must not erase edits they never recorded.
    previous = list(MATERIALS.overrides(world.id).values())
    payloads = {}
    def apply(key, digest):
        target, component, slot = key
        if digest is None:
            texture, operation = carla.TextureColor(1, 1), 'restore'
        else:
            _, texture = decode_texture(payloads[digest], (1024, 1024))
            operation = 'apply'
        world.apply_color_texture_to_object(f'{target}|csa|{component}|{slot}|{operation}',
                                           carla.MaterialParameter.Diffuse, texture)
        MATERIALS.record(world.id, target, component, slot, digest)
    transaction = MaterialTransaction(previous, document['environment_materials'], apply)
    catalog = MATERIALS.catalog(world.get_map().name)['actors']
    available = set(world.get_names_of_all_objects())
    for target, component, slot in transaction.changed:
        if target not in available: raise ValueError(f'Material target missing: {target}')
        entry = next((c for c in catalog.get(target, []) if c['component'] == component), None)
        if not entry or not any(s['slot'] == slot and s.get('status') == 'uv0_ready' for s in entry['slots']):
            raise ValueError(f'Material slot has no verified UV export: {target}/{component}/{slot}')
    for digest in set(transaction.before.values()) | set(transaction.desired.values()):
        payloads[digest] = MATERIALS.texture(digest)
    return transaction


@simulation_operation
def scene_history(data):
    connect_world()  # Reject during evaluation before changing the document cursor.
    saved = SCENES.move(data['scene_id'], int(data['direction']), data['expected_version'])
    try:
        return restore_scene({'scene_id': data['scene_id'], 'version': saved['head']['version']})
    except Exception:
        SCENES.move(data['scene_id'], -int(data['direction']), saved['head']['version'])
        raise


@simulation_operation
def update_actor(actor_id: int, transform_data: dict) -> dict:
    if evaluation_active():
        return evaluation_command("update", {"actor_id": actor_id,
                                              "transform": transform_data})
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


@simulation_operation
def duplicate_actor(actor_id: int) -> dict:
    if evaluation_active():
        return evaluation_command("duplicate", {"actor_id": actor_id})
    world = connect_world()
    actor = world.get_actor(actor_id)
    if not actor:
        raise RuntimeError(f"Actor {actor_id} is not running")
    transform = actor.get_transform()
    side, forward = transform.get_right_vector(), transform.get_forward_vector()
    width, length = actor.bounding_box.extent.y * 2 + 2, actor.bounding_box.extent.x * 2 + 2
    # A nearby wall or guardrail can obstruct one side. Try bounded alternatives.
    for offset in (side * width, side * -width, forward * length, forward * -length):
        try:
            return spawn_object(_generated_actor_assets.get(actor_id, actor.type_id), {
                "location": vector(transform.location + offset),
                "rotation": {"pitch": transform.rotation.pitch,
                             "yaw": transform.rotation.yaw, "roll": transform.rotation.roll}})
        except RuntimeError as exc:
            if "collision" not in str(exc).lower():
                raise
    raise RuntimeError("No collision-free position near this object; move it to an open area before duplicating")


@simulation_operation
def delete_actor(actor_id: int) -> dict:
    if evaluation_active():
        return evaluation_command("delete", {"actor_id": actor_id})
    world = connect_world()
    actor = world.get_actor(actor_id)
    if not actor:
        raise RuntimeError(f"Actor {actor_id} is not running")
    type_id = actor.type_id
    actor.destroy()
    _actor_object_names.pop(actor_id, None)
    _generated_actor_assets.pop(actor_id, None)
    _editor_actors.discard(actor_id)
    return {"ok": True, "actor_id": actor_id, "type_id": type_id}


@simulation_operation
def spawnable_blueprints(query: str, limit: int) -> dict:
    if evaluation_active():
        ids = list((evaluation_snapshot() or {}).get("blueprints", []))
        if query:
            ids = [item for item in ids if query.casefold() in item.casefold()]
        return {"ok": True, "total": len(ids), "blueprints": ids[:limit],
                "evaluation_active": True}
    world = connect_world()
    patterns = ("vehicle.*", "walker.pedestrian.*", "static.prop.*")
    ids = sorted({bp.id for pattern in patterns
                  for bp in world.get_blueprint_library().filter(pattern)})
    ids.extend(sorted(BLENDER.registry()))
    if query:
        ids = [item for item in ids if query.casefold() in item.casefold()]
    return {"ok": True, "total": len(ids), "blueprints": ids[:limit]}


@simulation_operation
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
        if len(matches) == 1:
            return matches[0]
    if actor.type_id == "vehicle.carlamotors.european_hgv":
        matches = sorted(name for name in names if name.startswith("BP_European_HGV_C_"))
        if len(matches) == 1:
            return matches[0]
    if actor.type_id == "walker.pedestrian.0001":
        matches = sorted(name for name in names if name.startswith("BP_Walker_Female1_v1_C_"))
        if len(matches) == 1:
            return matches[0]
    raise RuntimeError(
        f"Runtime mesh identity is unavailable for actor {actor.id} ({actor.type_id}); "
        "respawn it from Create Objects to register the mapping")


@simulation_operation
def scene_state() -> dict:
    global _scene_snapshot
    if evaluation_active():
        live = evaluation_snapshot()
        if live:
            hero = next((item for item in live.get("objects", []) if item.get("hero")), None)
            return {"ok": True, "runtime_mode": RUNTIME_MODE, "map": live["map"], "bounds": live["bounds"],
                    "road_points": live.get("road_points", []), "objects": live.get("objects", []),
                    "static_targets": [], "spectator": live["spectator"],
                    "hero_id": hero.get("id") if hero else None,
                    "hero_lock": False, "evaluation_active": True,
                    "updated_at": live.get("updated_at")}
        if _scene_snapshot is not None:
            return {**_scene_snapshot, "evaluation_active": True}
        return {"ok": True, "evaluation_active": True, "initializing": True,
                "map": "", "objects": [], "static_targets": [], "road_points": [],
                "bounds": {"min_x": 0, "max_x": 1, "min_y": 0, "max_y": 1},
                "spectator": None, "hero_id": None, "hero_lock": False,
                "runtime_mode": RUNTIME_MODE}
    world = connect_world()
    actors = [actor_record(actor) for actor in world.get_actors()
              if actor.type_id.startswith(("vehicle.", "walker.", "static.prop."))]
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
    _scene_snapshot = {"ok": True, "runtime_mode": RUNTIME_MODE, "map": map_name, "bounds": bounds,
            "road_points": cached["road_points"], "objects": actors,
            "static_targets": static_targets,
            "spectator": {"location": vector(spectator.location),
                          "rotation": {"yaw": spectator.rotation.yaw,
                                       "pitch": spectator.rotation.pitch}},
            "hero_id": hero.id if hero else None, "hero_lock": _hero_lock.is_set(),
            "evaluation_active": False}
    return _scene_snapshot


@simulation_operation
def focus_actor(actor_id: int) -> dict:
    if evaluation_active():
        return evaluation_command("focus_actor", {"actor_id": actor_id})
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


@simulation_operation
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


@simulation_operation
def focus_bev(x: float, y: float) -> dict:
    if evaluation_active():
        return evaluation_command("focus_bev", {"x": x, "y": y})
    world = connect_world()
    _hero_lock.clear()
    target = carla.Location(x=x, y=y, z=0.0)
    camera = carla.Location(x=x, y=y, z=55.0)
    world.get_spectator().set_transform(
        carla.Transform(camera, carla.Rotation(pitch=-90.0)))
    world.debug.draw_point(target + carla.Location(z=1.0), 0.35,
                           HIGHLIGHT_COLORS["road"], 5.0)
    return {"ok": True, "location": vector(target)}


@simulation_operation
def set_hero_lock(enabled: bool) -> dict:
    world = connect_world()
    hero = hero_actor(world)
    if enabled and not hero:
        raise RuntimeError("No vehicle with role_name=hero is running")
    _hero_lock.set() if enabled else _hero_lock.clear()
    return {"ok": True, "enabled": _hero_lock.is_set(),
            "hero_id": hero.id if hero else None}


@simulation_operation
def hero_follow_step():
    if not _hero_lock.is_set() or evaluation_active():
        return
    world = connect_world()
    hero = hero_actor(world)
    if not hero:
        _hero_lock.clear()
        return
    transform = hero.get_transform()
    forward = transform.get_forward_vector()
    location = transform.location
    camera = location + carla.Location(x=-forward.x*10.0, y=-forward.y*10.0, z=5.5)
    target = location + carla.Location(x=forward.x*6.0, y=forward.y*6.0, z=1.2)
    world.get_spectator().set_transform(carla.Transform(camera, look_at(camera, target)))


def hero_follow_loop():
    while True:
        try:
            hero_follow_step()
        except Exception as exc:
            print(f"hero follow warning: {exc}", flush=True)
        time.sleep(0.1)


@simulation_operation
def apply_livery(payload: bytes, actor_id: int | None = None) -> dict:
    image, texture = decode_texture(payload, (2048, 2048))

    if evaluation_active():
        if not actor_id:
            snapshot = evaluation_snapshot() or {}
            hero = next((item for item in snapshot.get("objects", []) if item.get("hero")), None)
            actor_id = int(hero["id"]) if hero else None
        if not actor_id:
            raise RuntimeError("Select a running vehicle before applying a texture")
        upload_dir = _evaluation_control_dir / "textures"
        upload_dir.mkdir(parents=True, exist_ok=True)
        texture_path = upload_dir / f"{uuid.uuid4().hex}.png"
        image.save(texture_path, format="PNG")
        try:
            return {"ok": True, **evaluation_command("apply_vehicle_texture", {
                "actor_id": actor_id, "texture_path": str(texture_path)})}
        except Exception:
            texture_path.unlink(missing_ok=True)
            raise

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


@simulation_operation
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


@simulation_operation
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


@simulation_operation
def apply_environment_texture(payload: bytes, object_id: int) -> dict:
    image, texture = decode_texture(payload, (1024, 1024))
    world = connect_world()
    category, obj = find_environment(world, object_id)
    names = set(world.get_names_of_all_objects())
    target = exact_environment_target(obj.name, names)
    if target is None:
        raise RuntimeError(
            f"The selected {category} object has no runtime material target: {obj.name}")
    world.apply_color_texture_to_object(
        target, carla.MaterialParameter.Diffuse, texture)
    return {"ok": True, "kind": category, "object_id": str(obj.id),
            "object_name": target, "resolution": [image.width, image.height]}


@simulation_operation
def material_catalog(object_id):
    world = connect_world()
    category, obj = find_environment(world, int(object_id))
    target = exact_environment_target(obj.name, set(world.get_names_of_all_objects()))
    catalog = MATERIALS.catalog(world.get_map().name)
    return {'ok':True, 'target':target, 'map':world.get_map().name.split('/')[-1],
            'category':category, 'components':catalog['actors'].get(target,[]),
            'overrides':[edit for edit in MATERIALS.overrides(world.id).values()
                         if edit['target'] == target]}


@simulation_operation
def apply_material_slot(data, payload=None):
    info = material_catalog(data['object_id'])
    component = str(data['component'])
    raw_slot = data['slot']
    if isinstance(raw_slot, bool) or not str(raw_slot).isdigit():
        raise ValueError('Material slot must be a non-negative integer')
    slot = int(raw_slot)
    if '|' in component or '|' in info['target']: raise ValueError('Invalid material target')
    entry = next((c for c in info['components'] if c['component'] == component), None)
    selected = next((s for s in entry['slots'] if s['slot']==slot), None) if entry else None
    if not selected or selected.get('status')!='uv0_ready':
        raise ValueError('This exact component/slot has no verified UV0 export')
    world = connect_world()
    if payload is None:
        texture = carla.TextureColor(1,1)
        operation, digest = 'restore', None
    else:
        image, texture = decode_texture(payload,(1024,1024))
        output = io.BytesIO(); image.save(output,format='PNG')
        digest = MATERIALS.put_texture(output.getvalue())
        operation = 'apply'
    world.apply_color_texture_to_object(f"{info['target']}|csa|{component}|{slot}|{operation}",
                                       carla.MaterialParameter.Diffuse, texture)
    MATERIALS.record(world.id,info['target'],component,slot,digest)
    return {'ok':True,'target':info['target'],'component':component,'slot':slot,'texture':digest,
            'operation':operation,'scope':'one component material slot','projection':'UV0'}


@simulation_operation
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
        if request.path in ('/materials/catalog', '/materials/mesh'):
            try:
                if request.path == '/materials/catalog':
                    result = material_catalog(params.get('object_id', [''])[0])
                else:
                    path = MATERIALS.mesh(params.get('map', [''])[0],
                                          params.get('file', [''])[0])
                    result = json.loads(path.read_text())
                self._headers()
                self.wfile.write(json.dumps(result).encode())
            except (ValueError, KeyError, OSError) as exc:
                self._headers(400)
                self.wfile.write(json.dumps({'ok': False, 'error': str(exc)}).encode())
            except RuntimeError as exc:
                self._headers(409)
                self.wfile.write(json.dumps({'ok': False, 'error': str(exc)}).encode())
            return
        if request.path in ('/scenes', '/scenes/document'):
            try:
                result = {'scenes': SCENES.list()} if request.path == '/scenes' else SCENES.read(params.get('scene_id',[''])[0], params.get('version',[None])[0])
                self._headers()
                self.wfile.write(json.dumps({'ok': True, **result}).encode())
            except (ValueError, OSError) as exc:
                self._headers(400)
                self.wfile.write(json.dumps({'ok': False, 'error': str(exc)}).encode())
            return
        if request.path in ('/system/preflight', '/session/status'):
            result = system_preflight() if request.path == '/system/preflight' else {'ok': True, 'session': SESSION.snapshot()}
            self._headers()
            self.wfile.write(json.dumps(result).encode())
            return
        if request.path in ('/datasets/projection','/datasets/trajectory'):
            try:
                params = parse_qs(request.query)
                if request.path == '/datasets/trajectory':
                    payload=replay_trajectory(DATASET_ROOT,params.get('run_id',[''])[0],
                        params.get('frame',['-1'])[0],float(params.get('horizon_s',['5'])[0]))
                else:
                    payload=replay_projection(DATASET_ROOT,params.get('run_id',[''])[0],
                        params.get('frame',['-1'])[0],params.get('camera',[''])[0])
                self._headers()
                self.wfile.write(json.dumps({'ok':True,**payload}).encode())
            except (ValueError,KeyError,OSError) as exc:
                self._headers(400)
                self.wfile.write(json.dumps({'ok':False,'error':str(exc)}).encode())
            return
        if request.path in ('/capture/status', '/capture/media', '/datasets/index', '/datasets/file', '/datasets/frame'):
            try:
                if request.path == '/capture/status':
                    path = _evaluation_control_dir/'capture/latest.json'
                    payload = json.loads(path.read_text()) if path.is_file() and evaluation_active() else None
                    if payload and path.stat().st_mtime < (_e2e_job.get('started_at') or 0):
                        payload = None
                    self._headers()
                    self.wfile.write(json.dumps({'ok': True, 'capture': payload}).encode())
                    return
                if request.path == '/datasets/index':
                    payload = replay_index(DATASET_ROOT, params.get('run_id', [''])[0])
                    self._headers()
                    self.wfile.write(json.dumps({'ok': True, **payload}).encode())
                    return
                if request.path == '/capture/media':
                    name = params.get('id', [''])[0]
                    allowed = {'CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT', 'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT', 'BEV_RGB', 'BEV_POINTS'}
                    allowed |= {'DEPTH_'+n for n in allowed if n.startswith('CAM_')}
                    if name not in allowed or not evaluation_active():
                        raise ValueError('Live sensor is unavailable')
                    frame = int(params.get('frame', ['-1'])[0])
                    path = _evaluation_control_dir/'capture'/'frames'/str(frame)/(name+'.jpg')
                    if path.stat().st_mtime < (_e2e_job.get('started_at') or 0):
                        raise ValueError('Sensor belongs to an earlier run')
                else:
                    name = 'frame.json' if request.path == '/datasets/frame' else params.get('name', [''])[0]
                    path = replay_file(DATASET_ROOT, params.get('run_id', [''])[0], params.get('frame', ['-1'])[0], name)
                payload = path.read_bytes()
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', FRONTEND_ORIGIN)
                self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(payload)
            except (ValueError, OSError) as exc:
                self._headers(404)
                self.wfile.write(json.dumps({'ok': False, 'error': str(exc)}).encode())
            return
        if request.path == '/scene/preview':
            try:
                payload = scene_preview()
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', FRONTEND_ORIGIN)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._headers(409)
                self.wfile.write(json.dumps({'ok': False, 'error': str(exc)}).encode())
            return
        if request.path == "/e2e/camera":
            camera_id = params.get("id", [""])[0]
            if camera_id not in {"CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT",
                                 "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"}:
                self._headers(404)
                self.wfile.write(b'{"ok":false,"error":"unknown camera"}')
                return
            path = _evaluation_control_dir / "telemetry" / f"{camera_id}.jpg"
            if not path.is_file():
                self._headers(404)
                self.wfile.write(b'{"ok":false,"error":"camera frame unavailable"}')
                return
            payload = path.read_bytes()
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", FRONTEND_ORIGIN)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
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
                min(200, max(1, int(params.get("limit", ["50"])[0]))),
                params.get("origin", ["all"])[0])
            self.wfile.write(json.dumps(result).encode())
        elif request.path == "/catalog/blueprints":
            result = spawnable_blueprints(params.get("q", [""])[0], 200)
            self.wfile.write(json.dumps(result).encode())
        elif request.path == "/scene/state":
            self.wfile.write(json.dumps(scene_state()).encode())
        elif request.path == "/e2e/status":
            self.wfile.write(json.dumps(e2e_status()).encode())
        elif request.path == "/e2e/telemetry":
            path = _evaluation_control_dir / "telemetry" / "latest.json"
            try:
                if not evaluation_active():
                    raise FileNotFoundError("No active inference; do not present stale frames as live")
                started = _e2e_job.get("started_at")
                if started and path.stat().st_mtime < started:
                    raise FileNotFoundError("Telemetry belongs to an earlier run")
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.wfile.write(json.dumps({"ok": True, "telemetry": payload}).encode())
            except (OSError, json.JSONDecodeError):
                self.wfile.write(b'{"ok":true,"telemetry":null}')
        elif request.path == "/e2e/benchmark/catalog":
            self.wfile.write(json.dumps({"ok": True,
                "routes": route_catalog(BENCH2DRIVE_ROOT),
                "algorithms": algorithm_catalog(
                    BENCH2DRIVE_ZOO, BENCH2DRIVE_TCP_ZOO)}).encode())
        elif request.path == "/e2e/benchmark/report":
            self.wfile.write(json.dumps({"ok": True,
                "report": benchmark_report(BENCH2DRIVE_ZOO)}).encode())
        elif request.path == "/datasets":
            self.wfile.write(json.dumps({"ok": True, "root": str(DATASET_ROOT),
                                         "datasets": list_datasets(DATASET_ROOT)}).encode())
        elif request.path == "/assets/uv-audit":
            self.wfile.write(json.dumps({"ok": True, **_uv_audit}).encode())
        elif request.path == "/blender/status":
            self.wfile.write(json.dumps(BLENDER.status()).encode())
        elif request.path == "/blender/registry":
            self.wfile.write(json.dumps({"ok": True, "assets": BLENDER.registry()}).encode())
        elif request.path == "/targets":
            kind = parse_qs(request.query).get("kind", [""])[0]
            self.wfile.write(json.dumps(texture_targets(kind)).encode())
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
                                "/scenario/compile", "/scenario/run", "/scenario/evaluate",
                                "/blender/create", "/blender/retexture",
                                "/blender/import", "/blender/spawn",
                                "/e2e/start", "/e2e/stop", "/collection/control", '/session/recover',
                                '/scenes/save', '/scenes/restore', '/scenes/history',
                                '/materials/apply', '/materials/restore', '/collection/start', '/collection/stop', '/collection/control'):
            self._headers(404)
            self.wfile.write(b'{"ok":false,"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 16 * 1024 * 1024:
                self._headers(413)
                self.wfile.write(b'{"ok":false,"error":"Request body exceeds 16 MiB limit"}')
                return
            payload = self.rfile.read(length)
            if request.path == '/collection/start':
                result = start_e2e({**json.loads(payload or b'{}'), 'action':'sensor-rig'})
            elif request.path == '/collection/control':
                result = manual_sensor_control(json.loads(payload or b'{}'))
            elif request.path == '/collection/stop':
                result = stop_sensor_rig(json.loads(payload or b'{}'))
            elif request.path == '/materials/apply':
                params = parse_qs(request.query)
                if not payload:
                    raise ValueError('Texture image is required')
                result = apply_material_slot({key: params.get(key, [''])[0]
                                              for key in ('object_id', 'component', 'slot')}, payload)
            elif request.path == '/materials/restore':
                result = apply_material_slot(json.loads(payload or b'{}'))
            elif request.path in ('/scenes/save', '/scenes/restore', '/scenes/history'):
                operation = {'/scenes/save': save_scene, '/scenes/restore': restore_scene, '/scenes/history': scene_history}[request.path]
                result = operation(json.loads(payload or b'{}'))
            elif request.path == '/session/recover':
                result = recover_session()
            elif request.path == '/collection/control':
                result = collection_request(json.loads(payload or b'{}'))
            elif request.path == "/e2e/start":
                result = start_e2e(json.loads(payload or b"{}"))
            elif request.path == "/e2e/stop":
                result = stop_e2e()
            elif request.path == "/scenario/evaluate":
                result = evaluate_scenario(json.loads(payload or b"{}"))
            elif request.path in ("/scenario/compile", "/scenario/run"):
                data = json.loads(payload or b"{}")
                result = compile_scenario(data, request.path.endswith("/run"))
            elif request.path in ("/blender/create", "/blender/retexture"):
                data = json.loads(payload or b"{}")
                if request.path.endswith("retexture") and not data.get("source_path"):
                    raise ValueError("source_path is required for retexture")
                result = BLENDER.run(data)
            elif request.path == "/blender/import":
                data = json.loads(payload or b"{}")
                result = BLENDER.import_to_carla(str(data["job_id"]), data.get("name"))
            elif request.path == "/blender/spawn":
                data = json.loads(payload or b"{}")
                result = spawn_object(str(data["blueprint_id"]), data.get("transform", {}))
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
                    int(data["object_id"]), data.get("visible", True))
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
        except (ValueError, KeyError) as exc:
            self._headers(400)
            self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode())
        except Exception as exc:
            self._headers(500)
            self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode())

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    # Do not pass a shell-inherited SIG_IGN to model subprocesses.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    print(f"CARLA livery bridge listening on http://{HOST}:{PORT}", flush=True)
    threading.Thread(target=resume_session, daemon=True).start()
    threading.Thread(target=hero_follow_loop, daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
