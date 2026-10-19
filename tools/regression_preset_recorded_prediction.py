"""Bounded three-sample preset recording, then production replay API checks."""
import json
import time
import uuid
from urllib.error import HTTPError
from pathlib import Path
from regression_e2e_lifecycle import request, wait_idle
from cleanup_superseded_model_captures import idle


def main():
    root = Path(__file__).resolve().parents[1]
    output = root/'runs/validation'/('preset-recorded-prediction-'+uuid.uuid4().hex)
    output.mkdir()
    report = {'passed': False, 'scope': 'three-sample TCP prediction persistence and replay API, not route completion'}
    execution = None
    try:
        idle()
        assert request('system/preflight')['ready']
        catalog = request('e2e/benchmark/catalog')
        collection = next(c['path'] for c in catalog['routes']['collections'] if c['name']=='bench2drive220.xml')
        request('e2e/start', {'action':'preset-run','algorithm':'tcp','collection':collection,'route_id':'26406'})
        execution = request('session/status')['session']['run_id']
        report['execution_id'] = execution
        command_path = root/'.runtime/evaluation-control/collection-request.json'
        before = command_path.read_bytes()
        report['foreign_command_rejections'] = []
        for recording in (True, False):
            try:
                request('collection/recording', {'run_id':'0'*32,'recording':recording})
                raise AssertionError('Foreign execution command accepted')
            except HTTPError as error:
                payload = json.loads(error.read())
                assert error.code == 400 and 'matching live' in payload.get('error',''), payload
                report['foreign_command_rejections'].append(payload)
            assert command_path.read_bytes() == before, 'Rejected command mutated recording request'
        deadline = time.monotonic()+180
        recording = False
        while time.monotonic()<deadline:
            session = request('session/status')['session']
            assert session['run_id']==execution and session['state']=='running', session
            capture = request('capture/status').get('capture') or {}
            if not recording and capture.get('prediction',{}).get('state')=='available':
                request('collection/recording', {'run_id':execution,'recording':True,'every':1,'max_frames':3})
                recording = True
            if recording and capture.get('recorded_frames')==3:
                report['run_id'] = capture['run_id']
                break
            time.sleep(1)
        else:
            raise TimeoutError('Three prediction samples not committed')
        request('collection/recording', {'run_id':execution,'recording':False})
        request('e2e/stop', {'run_id':execution})
        wait_idle()
        # Reaching the frame limit clears the live run_id; resolve the finalized
        # recording by exact execution identity, never by newest directory.
        if not report.get('run_id'):
            matches = []
            for path in (root/'.runtime/generated-scenarios').glob('*/manifest.json'):
                if path.is_symlink() or path.parent.is_symlink():
                    continue
                saved = json.loads(path.read_text())
                if saved.get('execution_id')==execution:
                    matches.append(path.parent.name)
            assert len(matches)==1, matches
            report['run_id'] = matches[0]
        dataset = root/'.runtime/generated-scenarios'/report['run_id']
        manifest = json.loads((dataset/'manifest.json').read_text())
        assert manifest['execution_id']==execution and manifest['frame_count']==3
        assert manifest['status'] in ('saved','saved_limit'), manifest
        index = json.loads((dataset/'index.json').read_text())
        report['frames'] = []
        for entry in index['frames']:
            frame = entry['frame']
            query = f'run_id={report["run_id"]}&frame={frame}'
            metadata = request('datasets/frame?'+query)
            trajectory = request('datasets/trajectory?'+query)
            assert metadata['prediction']['state']=='available', metadata['prediction']
            assert trajectory['prediction']['state']=='available', trajectory
            report['frames'].append({'frame':frame,'metadata_prediction':metadata['prediction'],'trajectory':trajectory})
        report['manifest'] = manifest
        report['allocated_raw_bytes'] = sum(p.stat().st_size for p in dataset.rglob('*') if p.is_file())
        report['passed'] = True
    finally:
        if execution:
            current = request('session/status')['session']
            if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
                try:
                    request('collection/recording', {'run_id':execution,'recording':False})
                finally:
                    request('e2e/stop', {'run_id':execution})
                    wait_idle()
        report['ready'] = request('system/preflight')['ready']
        report['passed'] = report['passed'] and report['ready']
        (output/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({'report':str(output/'report.json'),'passed':report['passed'],'run_id':report.get('run_id')}),flush=True)
    assert report['passed']


if __name__=='__main__':
    main()
