"""Read-only HTTP regression against existing native recordings."""
import argparse
import json
import urllib.error
from urllib.parse import urlencode

from regression_scene_versions import request
from carla_safety_agent.sensor_capture import CAMERAS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_id')
    parser.add_argument('frame', type=int)
    args = parser.parse_args()
    before = request('session/status')['session']
    counts = {}
    for camera in CAMERAS:
        query = {'run_id': args.run_id, 'frame': args.frame, 'camera': camera}
        result = request('datasets/boxes?' + urlencode(query))
        assert result['ok'] and result['frame'] == args.frame and result['camera'] == camera
        assert result['occlusion_checked'] is False
        assert result['source'] == 'recorded_native_world_vertices'
        for box in result['boxes']:
            assert 0 < len(box['segments']) <= 12
            for x1, y1, x2, y2 in box['segments']:
                assert all(0 <= x <= result['width']-1+1e-7 for x in (x1, x2))
                assert all(0 <= y <= result['height']-1+1e-7 for y in (y1, y2))
        counts[camera] = len(result['boxes'])
    for change in ({'camera': '../camera'}, {'frame': -1}, {'run_id': '../outside'}):
        query = {'run_id': args.run_id, 'frame': args.frame, 'camera': 'CAM_FRONT', **change}
        try:
            request('datasets/boxes?' + urlencode(query))
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            response = json.loads(exc.read())
            assert response['ok'] is False and response['error']
        else:
            raise AssertionError('Invalid replay request accepted')
    after = request('session/status')['session']
    assert (before['run_id'], before['state']) == (after['run_id'], after['state'])
    print(json.dumps({'run_id': args.run_id, 'frame': args.frame, 'boxes': counts,
                      'invalid_requests_rejected': 3, 'session_unchanged': True}))


if __name__ == '__main__':
    main()
