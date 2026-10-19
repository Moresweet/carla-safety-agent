import json
from pathlib import Path
import pytest
from carla_safety_agent.capture_recovery import recover_capture,inventory
from carla_safety_agent.capture_recovery import require_inactive_execution
from types import SimpleNamespace as NS


def fixture(tmp_path):
    source=tmp_path/'original';source.mkdir()
    (source/'manifest.json').write_text(json.dumps({'schema_version':'carla-safety-dataset/0.2',
        'run_id':'original','status':'recording','input_archive':'sensor_input.npz',
        'frame_count':200,'sampling_every_frames':1,'sensors':{'CAM_FRONT':{'samples':200}},
        'files':{'calibration':'calibration.json','index':'index.json'}}))
    (source/'calibration.json').write_text('{}')
    (source/'index.json').write_text('{broken')
    sample=source/'samples/0000000001';sample.mkdir(parents=True)
    (sample/'frame.json').write_text('{"frame":1,"timestamp":0.05}')
    (sample/'sensor_input.npz').write_bytes(b'unit fixture, not real sensor data')
    (source/'samples/0000000002').mkdir()
    (source/'samples/0000000002/partial.tmp').write_bytes(b'incomplete')
    destination=tmp_path/'copies';destination.mkdir()
    return source,destination


def test_zero_sample_capture_has_clear_error_and_no_copy(tmp_path):
    source=tmp_path/'zero';source.mkdir()
    destination=tmp_path/'copies';destination.mkdir()
    (source/'manifest.json').write_text(json.dumps({
        'schema_version':'carla-safety-dataset/0.2','status':'saved_capture_error',
        'input_archive':'sensor_input.npz','frame_count':0}))
    before=inventory(source)
    with pytest.raises(ValueError,match='没有已提交样本可恢复'):
        recover_capture(source,destination,'validator','python',lambda:None)
    assert inventory(source)==before
    assert list(destination.iterdir())==[]


@pytest.mark.parametrize('status', ['recording','saved_cleanup_error','saved_capture_error'])
def test_copy_reconstructs_index_retains_original_and_marks_recovery(tmp_path,monkeypatch,status):
    source,destination=fixture(tmp_path)
    path=source/'manifest.json';doc=json.loads(path.read_text());doc['status']=status
    if status=='saved_capture_error': doc.update(error='No space left on device',stop_reason='capture_io_error')
    path.write_text(json.dumps(doc))
    before=inventory(source);calls=[]
    monkeypatch.setattr('carla_safety_agent.capture_recovery.audit_capture',lambda *_:{'state':'passed'})
    output=recover_capture(source,destination,'validator','python',lambda:calls.append('inactive'))
    assert calls==['inactive','inactive'] and inventory(source)==before
    manifest=json.loads((output/'manifest.json').read_text())
    assert manifest['status']=='saved_recovered' and manifest['frame_count']==1
    assert manifest['run_id']==output.name and manifest['run_id']!='original'
    assert manifest['recovery']['omitted_uncommitted_tail']==['0000000002']
    assert not (output/'samples/0000000002').exists()
    assert json.loads((output/'index.json').read_text())['frames'][0]['frame']==1


def test_recovery_preserves_recording_projection_not_current_map(tmp_path,monkeypatch):
    from carla_safety_agent.map_projection_archive import archive_map_projection,read_map_projection
    source,destination=fixture(tmp_path)
    xml='<OpenDRIVE><header><geoReference>+proj=tmerc</geoReference></header></OpenDRIVE>'
    ref=archive_map_projection(source,NS(name='Town04',to_opendrive=lambda:xml))
    path=source/'manifest.json';doc=json.loads(path.read_text())
    doc['map_projection']=ref;doc['files']['map_projection']=ref['path'];path.write_text(json.dumps(doc))
    monkeypatch.setattr('carla_safety_agent.capture_recovery.audit_capture',lambda *_:{'state':'passed'})
    output=recover_capture(source,destination,'validator','python',lambda:None)
    restored=json.loads((output/'manifest.json').read_text())
    assert restored['map_projection']==ref
    assert read_map_projection(output,ref)==read_map_projection(source,ref)==xml


@pytest.mark.parametrize('damage',['symlink','interior','identity','saved','active'])
def test_preflight_failure_never_creates_copy(tmp_path,damage):
    source,destination=fixture(tmp_path)
    if damage=='symlink':(source/'linked').symlink_to(source/'calibration.json')
    if damage=='interior':
        folder=source/'samples/0000000003';folder.mkdir();(folder/'frame.json').write_text('{"frame":3,"timestamp":0.15}')
    if damage=='identity':(source/'samples/0000000001/frame.json').write_text('{"frame":true,"timestamp":0.05}')
    if damage=='saved':
        path=source/'manifest.json';doc=json.loads(path.read_text());doc['status']='saved';path.write_text(json.dumps(doc))
    def inactive():
        if damage=='active':raise ValueError('active owner')
    with pytest.raises(ValueError):recover_capture(source,destination,'validator','python',inactive)
    assert not list(destination.iterdir())


@pytest.mark.parametrize('damage',['raw','changed','owner'])
def test_failed_copy_is_not_finalized_or_removed(tmp_path,monkeypatch,damage):
    source,destination=fixture(tmp_path);before=inventory(source);calls=[]
    def audit(*_):
        if damage=='changed':(source/'calibration.json').write_text('{"changed":true}')
        return {'state':'failed' if damage=='raw' else 'passed'}
    def inactive():
        calls.append(1)
        if damage=='owner' and len(calls)>1:raise ValueError('owner resumed')
    monkeypatch.setattr('carla_safety_agent.capture_recovery.audit_capture',audit)
    with pytest.raises(RuntimeError,match='original untouched'):recover_capture(source,destination,'validator','python',inactive)
    output=next(destination.iterdir())
    assert json.loads((output/'recovery.json').read_text())['state']=='failed'
    assert json.loads((output/'manifest.json').read_text())['status']=='recovery_pending'
    if damage!='changed':assert inventory(source)==before


@pytest.mark.parametrize('case',['dead','reused','alive','active','unknown','bad_identity'])
def test_worker_absence_is_checked_strictly(monkeypatch,case):
    identity={'pid':123,'start_ticks':'456'}
    record={'process':identity if case!='bad_identity' else {'pid':123,'start_ticks':'invalid'}}
    monkeypatch.setattr('carla_safety_agent.session.SessionJournal',lambda _:NS(
        snapshot=lambda:{'state':'running' if case=='active' else 'completed'},read_execution=lambda _:record))
    def observe(_):
        if case=='unknown':raise PermissionError('cannot inspect owner')
        return identity if case=='alive' else {'pid':123,'start_ticks':'789'} if case=='reused' else None
    monkeypatch.setattr('carla_safety_agent.session.observed_process_identity',observe)
    if case in ('dead','reused'):require_inactive_execution('/data','execution')
    else:
        with pytest.raises((ValueError,PermissionError)):require_inactive_execution('/data','execution')
