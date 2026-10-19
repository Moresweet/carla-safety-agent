#!/usr/bin/env python3
"""Exercise real model lifecycle through the same API used by the visible UI."""
import argparse
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image


def request(path, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request('http://127.0.0.1:8765/' + path, data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=40) as response:
        return json.load(response)


def wait_idle(timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = request('e2e/status')['job']
        if job['state'] not in ('running', 'stopping'):
            return job
        time.sleep(1)
    raise RuntimeError('Evaluation did not stop cleanly')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--models', nargs='+', default=['vad', 'tcp', 'admlp', 'uniad-tiny', 'uniad-base', 'vad'])
    parser.add_argument('--route', default='26406')
    parser.add_argument('--advance-frames', type=int, default=12)
    parser.add_argument('--inference-timeout', type=int, default=240)
    parser.add_argument('--require-planning-origin', action='store_true')
    args = parser.parse_args()
    if not 12<=args.advance_frames<=5000:parser.error('advance-frames must be 12..5000')
    if not 30<=args.inference_timeout<=7200:parser.error('inference-timeout must be 30..7200 seconds')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    catalog = request('e2e/benchmark/catalog')
    collection = next(c['path'] for c in catalog['routes']['collections']
                      if c['name'] == 'bench2drive220.xml')
    wait_idle(5)
    reports = []
    for index, model in enumerate(args.models):
        report = {'model': model, 'route': args.route, 'passed': False,
                  'scope':'inference lifecycle with deliberate early stop; not route completion',
                  'requested_advance_frames':args.advance_frames}
        reports.append(report)
        try:
            print(f'START {model}', flush=True)
            payload = dict(action='preset-run', algorithm=model, collection=collection, route_id=args.route)
            assert request('e2e/start', payload)['ok']
            launch_session = request('session/status')['session']
            report['execution_id'] = launch_session['run_id']
            report['starting_scene'] = launch_session['configuration']['starting_scene']
            assert report['starting_scene']['map']
            assert isinstance(report['starting_scene']['objects'], list)
            assert report['starting_scene']['weather']
            assert 'environment_materials' in report['starting_scene']
            assert 'hidden_environment' in report['starting_scene']
            assert report['starting_scene']['limitations']
            try:
                request('e2e/start', payload)
                raise AssertionError('Duplicate start was accepted')
            except urllib.error.HTTPError as exc:
                assert exc.code >= 400
            report['duplicate_rejected'] = True
            deadline = time.monotonic() + args.inference_timeout
            first = None
            while time.monotonic() < deadline:
                status = request('e2e/status')
                if status['job']['state'] != 'running':
                    raise RuntimeError(status['log'][-2500:])
                # Polling the editor while loading must not compete for CARLA.
                assert request('scene/state')['evaluation_active']
                telemetry = request('e2e/telemetry').get('telemetry')
                if telemetry and telemetry['frame'] > 3:
                    first = first or telemetry['frame']
                    if telemetry['frame'] >= first + args.advance_frames:
                        break
                time.sleep(2)
            else:
                raise RuntimeError('Inference did not advance before deadline')
            report['frames'] = [first, telemetry['frame']]
            report['telemetry'] = telemetry
            if args.require_planning_origin:
                capture = request('capture/status')['capture']
                report['planning_capture'] = capture
                assert capture['prediction']['state'] == 'available', capture['prediction']
                assert capture['planning_observed_calls'] > 0
                assert capture['planning_anchor']['frame'] <= capture['frame']
                assert capture['prediction']['anchor'] == capture['planning_anchor']
                assert capture['prediction']['timing_verified'] is False
                assert capture['recording'] is False
            assert telemetry['outputs']['trajectory_ego_m']
            report['cameras'] = {}
            for camera in telemetry['inputs']['camera_ids']:
                raw = urllib.request.urlopen('http://127.0.0.1:8765/e2e/camera?id='+camera, timeout=15).read()
                Image.open(io.BytesIO(raw)).verify()
                (output/f'{index}-{model}-{camera}.jpg').write_bytes(raw)
                report['cameras'][camera] = len(raw)
            request('e2e/stop', {'run_id':report['execution_id']})
            report['stop'] = wait_idle()
            assert report['stop']['state'] == 'stopped', report['stop']
            assert not report['stop'].get('cleanup_error'), report['stop']
            report['session'] = request('session/status')['session']
            assert report['session']['run_id'] == report['execution_id']
            assert report['session']['configuration']['starting_scene'] == report['starting_scene']
            assert report['session']['state'] == 'stopped', report['session']
            assert not report['session'].get('error'), report['session']
            report['preflight'] = request('system/preflight')
            assert report['preflight']['ready'], report['preflight']
            native = next(check for check in report['preflight']['checks'] if check['id'] == 'carla')
            assert native['synchronous'] is False, native
            assert request('scene/state')['ok']
            assert request('e2e/telemetry')['telemetry'] is None
            report['passed'] = True
            print(f'PASS {model} frames={report["frames"]}', flush=True)
        except Exception as exc:
            report['error'] = str(exc)
            print(f'FAIL {model}: {exc}', flush=True)
            current=request('session/status')['session']
            if current['run_id']==report.get('execution_id'):
                request('e2e/stop', {'run_id':current['run_id']})
            wait_idle()
            raise
        finally:
            (output/'report.json').write_text(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
