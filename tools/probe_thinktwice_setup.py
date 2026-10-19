"""Run actual adapter setup without constructing a CARLA client or driving."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('thinktwice', 'driveadapter'), default='thinktwice')
    parser.add_argument('--model-root', type=Path, required=True)
    parser.add_argument('--benchmark-root', type=Path, required=True)
    parser.add_argument('--carla-root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--synthetic-steps', action='store_true',
                        help='Exercise original preprocessing and controller on synthetic tick data, never real sensors')
    args = parser.parse_args()
    if args.report.exists() or not args.report.parent.is_dir():
        parser.error('Report must be a new file in an existing directory')
    repo = Path(__file__).resolve().parents[1]
    dependencies = repo / '.runtime/external-models'
    model_root = args.model_root.resolve()
    sys.path[:0] = [str(dependencies / 'cumm-compatible'),
        str(dependencies / 'legacy-python'), str(dependencies / 'mmdetection3d-1.0'),
        str(args.carla_root.resolve() / 'PythonAPI/carla'),
        str(args.benchmark_root.resolve() / 'leaderboard'),
        str(args.benchmark_root.resolve() / 'scenario_runner'), str(repo / 'src')]
    report = {'ok': False, 'world_modified': False,
              'scope': 'Real adapter setup only; constructor, sensors and driving not exercised'}
    try:
        import torch
        import mmcv
        mmcv.__path__.append(str(dependencies / 'mmcv-full-1.7.0/mmcv'))
        # Original training directory contains code/, which shadows stdlib
        # code during Torch's debugger imports if inserted too early.
        import leaderboard
        if Path(leaderboard.__file__).resolve() != (args.benchmark_root.resolve() / 'leaderboard/leaderboard/__init__.py'):
            raise RuntimeError('Setup probe did not select the host leaderboard package')
        sys.path.insert(0, str(model_root / 'leaderboard'))
        sys.path.extend([str(model_root), str(model_root / 'open_loop_training')])
        with tempfile.TemporaryDirectory(prefix='thinktwice-setup-') as output:
            os.environ['SAVE_PATH'] = output
            os.environ['ROUTES'] = 'setup-probe.xml'
            spec = importlib.util.spec_from_file_location('csa_thinktwice_setup',
                repo / f'integration/opendrive/{args.model}_agent.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls = getattr(module, module.get_entry_point())
            adapter = cls.__new__(cls)
            weights = 'thinktwice-189k.pth' if args.model == 'thinktwice' else 'driveadapter-189k.pth'
            adapter.setup(str(model_root / weights) + '+' +
                          str(model_root / f'open_loop_training/configs/{args.model}.py'))
            torch.cuda.synchronize()
            from carla_safety_agent.prediction_trajectory import controller_digest, CONTROLLERS
            digest = controller_digest(adapter.model.control_pid.__func__)
            if args.model == 'thinktwice':
                assert digest == CONTROLLERS['thinktwice'], 'Loaded PID source does not match reviewed contract'
            report.update(ok=True, checkpoint=adapter.model._csa_checkpoint_evidence,
                          controller_sha256=digest,
                          device=str(next(adapter.model.parameters()).device),
                          history_queue=type(adapter.data_queue).__name__,
                          sensor_ids=[s['id'] for s in adapter.sensors()],
                          single_frame_pipeline=repr(adapter.test_pipeline),
                          temporal_pipeline=repr(adapter.seq_test_pipeline))
            if args.synthetic_steps:
                import numpy as np
                from carla_safety_agent.opendrive_history import FrameIdentity
                report['ok'] = False
                report['scope'] = 'Original run_step with synthetic tick outputs; no real sensors, route planner or vehicle'
                adapter.initialized = True
                adapter.update_gps_buffer = lambda *args: None
                if args.model == 'driveadapter':
                    # Explicit synthetic route input, not a real route-planner
                    # test. Leave original union2one/network/control unchanged.
                    adapter.generate_route_mask = lambda: np.zeros((192, 192), dtype=np.uint8)
                    report['synthetic_route_mask'] = True
                rng = np.random.default_rng(321)
                points = rng.random((10000, 4), dtype=np.float32)
                points[:, :3] = points[:, :3] * [36, 36, 6] + [-7, -18, -3]
                tick = {'theta': 0., 'x': 0., 'y': 0., 'speed': 0.,
                        'x_target': 10., 'y_target': 0., 'next_command': 4,
                        'acceleration': np.zeros(3), 'angular_velocity': np.zeros(3),
                        'lidar': points}
                tick.update({camera: np.zeros((900, 1600, 3), dtype=np.uint8)
                             for camera in adapter.cfg['camera_list']})
                def synthetic_tick(data):
                    adapter.step += 1
                    return tick
                adapter.tick = synthetic_tick
                calls = []
                original_forward = adapter.model.forward_inference
                def observe_forward(batch, *extra):
                    calls.append({'image_shape': list(batch['img'].shape)})
                    return original_forward(batch, *extra)
                adapter.model.forward_inference = observe_forward
                for frame in range(32):
                    adapter.set_simulator_frame(FrameIdentity(1, frame, frame*.05))
                    control = adapter.run_step({}, frame*.05)
                    assert np.isfinite([control.steer, control.throttle, control.brake]).all()
                torch.cuda.synchronize()
                assert len(calls) == 1, 'Warmup frames must not count as model inference'
                report.update(ok=True, synthetic_steps={'frames': 32, 'inferences': calls,
                    'control': {'steer': control.steer, 'throttle': control.throttle,
                                'brake': control.brake}, 'driving_quality_verified': False})
    except Exception as error:
        report.update(error=str(error), traceback=traceback.format_exc())
    with args.report.open('x') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
