#!/usr/bin/env python3
"""Observe an explicitly started evaluation and exercise its editor command queue."""
import argparse
import io
import json
import time
import urllib.request
from pathlib import Path
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    base = 'http://127.0.0.1:8765/'
    def get(path):
        return json.load(urllib.request.urlopen(base+path, timeout=45))
    def post(path, data=None, png=None):
        body = png if png is not None else json.dumps(data).encode()
        return json.load(urllib.request.urlopen(urllib.request.Request(base+path, data=body,
            headers={'Content-Type':'image/png' if png is not None else 'application/json'}), timeout=90))
    assert get('e2e/status')['job']['state'] == 'running', 'Start evaluation first'
    deadline = time.monotonic()+180
    while time.monotonic()<deadline:
        telemetry = get('e2e/telemetry').get('telemetry')
        if telemetry and telemetry['frame']>3:
            break
        if get('e2e/status')['job']['state'] != 'running':
            raise RuntimeError('Evaluation exited before inference')
        time.sleep(2)
    else:
        raise RuntimeError('Inference did not become ready')
    first = telemetry
    state = get('scene/state')
    hero = next(o for o in state['objects'] if o.get('hero'))
    report = {'hero':hero, 'first':first, 'focus':[], 'cameras':{}}
    start = time.monotonic()
    for index in range(3):
        report['focus'].append(post('focus/actor', {'actor_id':hero['id']}))
    data = io.BytesIO()
    Image.new('RGB',(64,64),(255,0,160)).save(data,format='PNG')
    report['texture'] = post('apply?actor_id='+str(hero['id']),png=data.getvalue())
    assert 'lamppost' not in report['texture']['object_name'].lower(), 'Texture incorrectly targeted a lamp'
    for camera in telemetry['inputs']['camera_ids']:
        raw = urllib.request.urlopen(base+'e2e/camera?id='+camera,timeout=30).read()
        image = Image.open(io.BytesIO(raw))
        image.verify()
        (output/(camera+'.jpg')).write_bytes(raw)
        report['cameras'][camera] = len(raw)
    while time.monotonic()-start<60:
        assert get('e2e/status')['job']['state']=='running', 'Unexpected evaluation exit'
        time.sleep(2)
    report['last'] = get('e2e/telemetry')['telemetry']
    report['duration_wall_s'] = time.monotonic()-start
    assert report['last']['frame']>first['frame'], 'Inference frame did not advance'
    assert len(report['last']['outputs']['trajectory_ego_m'])>0, 'Missing predicted trajectory'
    (output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'frames':[first['frame'],report['last']['frame']],
        'cameras':report['cameras'],'texture':report['texture'],'duration':report['duration_wall_s']}),flush=True)


if __name__ == '__main__':
    main()
