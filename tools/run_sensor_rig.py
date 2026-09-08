"""Session-owned standalone capture worker. Launch through the studio bridge."""
import argparse
import json
import os
import signal
import time
from pathlib import Path

import carla
from carla_safety_agent.evaluation_control import EvaluationControl
from carla_safety_agent.sensor_capture import SensorCapture, atomic_json
from carla_safety_agent.session import SessionJournal
from carla_safety_agent.manual_control import current_control

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=2000)
    parser.add_argument('--frames', type=int, default=200)
    parser.add_argument('--mode', choices=('stationary','autopilot','manual'), default='stationary')
    args = parser.parse_args()
    if not 10 <= args.frames <= 100000: raise ValueError('frames must be 10..100000')
    # Popen returns before the bridge durably attaches the child's identity.
    deadline = time.monotonic()+10
    while SessionJournal(ROOT/'data').owned_pid() != os.getpid():
        if time.monotonic() > deadline: raise RuntimeError('No verified studio session owns this worker')
        time.sleep(.05)
    runtime = Path(os.environ['CSA_EVALUATION_CONTROL_DIR'])
    client = carla.Client('127.0.0.1',args.port)
    client.set_timeout(15)
    world = client.get_world()
    previous = world.get_settings()
    if previous.synchronous_mode: raise RuntimeError('Another synchronous owner is already active')
    ego = capture = manager = None
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    report = {'source':'sensor-rig','mode':args.mode,'frames':0,'recorded_frames':0}
    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = .05
        world.apply_settings(settings)
        blueprint = world.get_blueprint_library().find('vehicle.lincoln.mkz_2020')
        blueprint.set_attribute('role_name','sensor_rig')
        for transform in world.get_map().get_spawn_points():
            if stopped: break
            ego = world.try_spawn_actor(blueprint, transform)
            if ego: break
        if not ego: raise RuntimeError('No free spawn point for the capture vehicle')
        if args.mode == 'autopilot':
            manager = client.get_trafficmanager(8050)
            manager.set_synchronous_mode(True)
            manager.set_random_device_seed(42)
            ego.set_autopilot(True,8050)
        else:
            ego.apply_control(carla.VehicleControl(brake=1,hand_brake=True))
        capture = SensorCapture(world,ego,[],runtime,source='sensor-rig')
        control = EvaluationControl(runtime)
        for _ in range(args.frames):
            if stopped: break
            if args.mode=='manual':
                try: command=json.loads((runtime/'manual-control.json').read_text())
                except (OSError,ValueError): command=None
                values=current_control(command,os.environ.get('CSA_EXECUTION_ID'),time.monotonic())
                ego.apply_control(carla.VehicleControl(**values))
            frame = world.tick(15)
            capture.process_frame(frame,ego.get_control())
            control.on_frame(world)
            report.update(frames=report['frames']+1,recorded_frames=capture.count,
                          run_id=getattr(capture,'run_id',None),error=capture.error)
            atomic_json(runtime/'sensor-rig-status.json',report)
            if getattr(capture,'stop_reason',None):
                report['stop_reason']=capture.stop_reason
                break  # Valid samples reached an explicit recording bound, not a process failure.
            if capture.error: raise RuntimeError(capture.error)
        report['stopped'] = stopped
    finally:
        errors = []
        if capture:
            try: errors.extend(capture.close())
            except Exception as exc: errors.append(str(exc))
        if ego and manager:
            # Unregister before destruction: TM's worker may otherwise dereference
            # the destroyed actor during asynchronous shutdown and abort natively.
            try: ego.set_autopilot(False,8050)
            except Exception as exc: errors.append(str(exc))
        if ego:
            try:
                if ego.destroy() is False: errors.append('Capture vehicle destroy returned false')
            except Exception as exc: errors.append(str(exc))
        if manager:
            try: manager.set_synchronous_mode(False)
            except Exception as exc: errors.append(str(exc))
        try: world.apply_settings(previous)
        except Exception as exc: errors.append(str(exc))
        report['cleanup_errors'] = errors
        atomic_json(runtime/'sensor-rig-status.json',report)
        print(json.dumps(report),flush=True)
        if errors: raise RuntimeError('Capture cleanup incomplete: '+ '; '.join(errors))


if __name__ == '__main__': main()
