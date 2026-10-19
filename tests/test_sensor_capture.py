import json
from types import SimpleNamespace
import numpy as np
import pytest
from carla_safety_agent.sensor_capture import depth_meters, bev_preview, calibration
from carla_safety_agent.provenance import ActorProvenance
from carla_safety_agent.replay import replay_file, replay_index
from carla_safety_agent.uv_audit import audit_uv
from carla_safety_agent.sensor_capture import SensorCapture, CAMERAS


@pytest.mark.parametrize('recording', [True, False])
@pytest.mark.parametrize('active', [True, False])
def test_old_execution_recording_command_does_not_change_current_capture(tmp_path, monkeypatch, recording, active):
    monkeypatch.setenv('CSA_EXECUTION_ID', 'new')
    capture=object.__new__(SensorCapture)
    capture.root=tmp_path; capture.run=tmp_path if active else None
    capture.last_request='current'; capture.every=2
    capture._accepted_recording_request={'id':'current','recording':active,'every':2,'max_frames':3}
    (tmp_path/'collection-request.json').write_text(json.dumps({'id':'old-command','execution_id':'old','recording':recording}))
    request=capture.request()
    assert request['recording'] is active and request['id']=='current'
    assert request['every']==2 and request['max_frames']==3


def test_matching_execution_recording_command_is_read(tmp_path, monkeypatch):
    monkeypatch.setenv('CSA_EXECUTION_ID', 'new')
    capture=object.__new__(SensorCapture); capture.root=tmp_path
    command={'id':'request','execution_id':'new','recording':True,'every':1,'max_frames':3}
    (tmp_path/'collection-request.json').write_text(json.dumps(command))
    assert capture.request()==command


def test_depth_channel_order_and_units():
    values = np.array([[[0,0,0,255], [255,255,255,255], [0,0,1,255]]], dtype=np.uint8)
    meters = depth_meters(values)
    assert meters.dtype == np.float32
    assert meters[0,0] == 0
    assert meters[0,1] == pytest.approx(1000)
    assert meters[0,2] == pytest.approx(1000/16777215)


def test_close_reports_failed_destroy_and_continues_other_cleanup():
    import threading
    capture=object.__new__(SensorCapture);capture.lock=threading.Condition()
    calls=[]
    failed=SimpleNamespace(is_alive=True,stop=lambda:None,destroy=lambda:False)
    good=SimpleNamespace(is_alive=True,stop=lambda:None,destroy=lambda:calls.append('destroy') or True)
    capture.sensors=[failed,good];capture.run=None
    capture.manifest=lambda status:calls.append(status)
    errors=capture.close()
    assert errors and 'returned false' in errors[0]
    assert capture.sensors==[failed]
    assert calls==['destroy','saved_cleanup_error']


def test_close_reports_manifest_failure():
    import threading
    capture=object.__new__(SensorCapture);capture.lock=threading.Condition();capture.sensors=[];capture.run=None
    def fail(status): raise OSError('disk full')
    capture.manifest=fail
    assert 'disk full' in capture.close()[0]


def test_write_failure_is_not_finalized_as_success(tmp_path):
    import errno
    import threading
    capture=object.__new__(SensorCapture)
    capture.live=tmp_path
    capture.lock=threading.Condition();capture.sensors=[];capture.run=None
    statuses=[]
    capture.manifest=lambda status:statuses.append(status)
    def fail(*args, **kwargs): raise OSError(errno.ENOSPC,'No space left on device')
    capture._process=fail
    with pytest.raises(OSError): capture.process({},None,None)
    assert capture.stop_reason == 'capture_io_error'
    assert 'No space left' in capture.error
    assert capture.close() == []
    assert statuses == ['saved_capture_error']


def test_sample_reserve_accounts_for_raw_and_derived_arrays():
    from carla_safety_agent.sensor_capture import sample_storage_reserve
    rgb=np.zeros((360,640,4),dtype=np.uint8)
    lidar=np.zeros((6400,4),dtype=np.float32)
    reserve=sample_storage_reserve({'camera':rgb},{'camera':rgb},{'depth':rgb,'LIDAR':lidar})
    assert reserve>rgb.nbytes*3+lidar.nbytes+16*1024**2
    assert sample_storage_reserve({}, {}, {})==16*1024**2


def test_lidar_bev_orientation():
    view = bev_preview(np.array([[10,10,1,.5], [np.nan,0,0,0]]), size=600, extent=60)
    assert view.shape == (600,600,3)
    assert (view[250,350] != [9,18,29]).any()


def test_calibration_focal():
    c = calibration(dict(type='sensor.camera.rgb', width=640, height=360, fov=90))
    assert c['K'][0][0] == pytest.approx(320)
    assert c['K'][1][2] == 180


def test_sensor_extrinsics_and_optical_basis():
    spec=dict(type='sensor.camera.rgb',width=640,height=360,fov=90,x=2,y=3,z=4,yaw=90)
    c=calibration(spec)
    transform=np.asarray(c['sensor_to_ego'])
    assert transform @ [1,0,0,1] == pytest.approx([2,4,4,1])
    assert transform @ np.asarray(c['ego_to_sensor']) == pytest.approx(np.eye(4))
    assert np.asarray(c['sensor_to_optical']) @ [10,2,3,1] == pytest.approx([2,-3,10,1])
    assert 'sensor_to_ego' not in calibration(dict(type='sensor.speedometer'))


def test_provenance_survives_restart_not_episode_change(tmp_path):
    actor = SimpleNamespace(id=12, type_id='vehicle.test')
    path = tmp_path/'origins.json'
    ActorProvenance(path).mark(1,[actor],'user')
    restored = ActorProvenance(path)
    assert restored.origin(1,actor) == 'user'
    restored.mark(1,[actor],'evaluation',overwrite=False)
    assert restored.origin(1,actor) == 'user'
    assert restored.origin(2,actor) == 'unknown'
    assert restored.origin(1,SimpleNamespace(id=12,type_id='walker.test')) == 'unknown'


def test_replay_is_confined_to_indexed_frames(tmp_path):
    run=tmp_path/'test'; folder=run/'samples'/'0000000001';folder.mkdir(parents=True)
    (run/'manifest.json').write_text('{}')
    (run/'index.json').write_text(json.dumps({'frames':[{'frame':1,'path':'samples/0000000001'}]}))
    (folder/'frame.json').write_text('{}')
    assert replay_file(tmp_path,'test',1,'frame.json') == folder/'frame.json'
    for name in ('../manifest.json','/etc/passwd'):
        with pytest.raises(ValueError): replay_file(tmp_path,'test',1,name)
    with pytest.raises(ValueError): replay_file(tmp_path,'test',2,'frame.json')
    with pytest.raises(ValueError): replay_index(tmp_path,'../test')


def test_uv_audit_reports_missing_and_invalid(tmp_path):
    (tmp_path/'vehicle-mesh-catalog.json').write_text(json.dumps({'a':{'url':'/a.json'}, 'b':{'url':'/b.json'}}))
    (tmp_path/'a.json').write_text(json.dumps({'vertices':[0]*15}))
    audit = audit_uv(tmp_path)
    assert audit['exported'] == 1
    assert audit['assets']['b']['status'] == 'missing_export'
    assert audit['other_categories'] == 'not_exported'


@pytest.mark.parametrize('with_scenario', [False, True])
@pytest.mark.parametrize('limit_reason', ['frame_limit','storage_limit','disk_reserve','capture_quota','quota_unknown'])
@pytest.mark.parametrize('write_failure', ['npz','png','index','manifest'])
def test_standalone_capture_records_real_rig_arrays_without_model_claim(tmp_path, monkeypatch, with_scenario, limit_reason, write_failure):
    import threading
    capture = object.__new__(SensorCapture)
    capture.source = 'sensor-rig'
    capture.scenario = {'scenario_id':'rule-test', 'seed':7, 'environment':{'precipitation':20}} if with_scenario else None
    capture.root = tmp_path/'runtime'
    capture.live = capture.root/'capture'
    capture.live.mkdir(parents=True)
    capture.lock = threading.Condition()
    capture.closed = False
    capture.run = capture.last_request = None
    capture.count = capture.skipped = capture.bytes = capture.sequence = 0
    capture.frame_index, capture.live_generations = [], []
    capture.error = None
    capture.map_name = 'Town04'
    image = np.full((2,2,4), [20,40,60,255], dtype=np.uint8)
    samples = {n:image for n in CAMERAS}
    samples.update({'DEPTH_'+n:np.zeros((2,2,4),dtype=np.uint8) for n in CAMERAS})
    samples.update(LIDAR=np.array([[1,2,3,.5]],dtype=np.float32), BEV_RGB=image)
    capture.samples = {name:{12:value} for name,value in samples.items()}
    capture.auxiliary = set(samples)
    capture.specs = {name:{} for name in samples}
    capture.request = lambda: {'recording':True,'id':'record','every':1,'max_frames':2}
    capture.world = SimpleNamespace(get_snapshot=lambda:SimpleNamespace(frame=12,timestamp=SimpleNamespace(elapsed_seconds=.6)),
                                    get_actors=lambda:[])
    capture.ego = SimpleNamespace(id=3,get_transform=lambda:SimpleNamespace(get_matrix=lambda:np.eye(4).tolist()),
                                  get_velocity=lambda:SimpleNamespace(x=0,y=0,z=0))
    monkeypatch.setenv('CSA_DATASET_ROOT',str(tmp_path/'datasets'))
    monkeypatch.setenv('CSA_EXECUTION_ID','verified-session-id')
    capture.process_frame(12,SimpleNamespace(steer=0,throttle=0,brake=1))
    assert capture.count == 1
    manifest = json.loads((capture.run/'manifest.json').read_text())
    assert manifest['family']=='sensor-rig' and manifest['model'] is None
    assert manifest['execution_id']=='verified-session-id'
    assert manifest['capture_quota_policy']['valid'] is True
    assert manifest['capture_quota_policy']['limit_bytes'] == capture.quota_policy['limit_bytes']
    if with_scenario:
        from carla_safety_agent.scenario_archive import read_verified_scenario
        reference = manifest['scenario']
        saved, digest = read_verified_scenario(capture.run/reference['path'], reference['sha256'])
        assert saved == capture.scenario
        assert manifest['scenario_id'] == saved['scenario_id'] == 'rule-test'
        assert manifest['files']['scenario'] == reference['path']
    else:
        assert manifest['scenario'] is None and 'scenario' not in manifest['files']
    folder = capture.run/'samples'/'0000000012'
    meta = json.loads((folder/'frame.json').read_text())
    assert meta['synchronized'] and meta['actual_model_inputs']==[] and meta['model'] is None
    assert not (folder/'model_input.npz').exists()
    with np.load(folder/'sensor_input.npz') as arrays:
        assert set(arrays.files)==set(CAMERAS)
        assert np.array_equal(arrays['CAM_FRONT'],image)
    import subprocess
    import sys
    from pathlib import Path
    checker = Path(__file__).resolve().parents[1]/'tools/validate_capture_dataset.py'
    subprocess.run([sys.executable,str(checker),str(capture.run)],check=True)
    # Exercise the CLI validator across both actual input storage formats.
    # These are synthetic test samples, never rewrite a user's recording.
    model_manifest = dict(manifest, input_archive='model_input.npz')
    (capture.run/'manifest.json').write_text(json.dumps(model_manifest))
    model_meta = dict(meta, model='test-model', actual_model_inputs=[*CAMERAS, 'SPEED'],
                      sensor_frames={name:meta['frame'] for name in (*CAMERAS,'SPEED')},
                      input_scalars={'SPEED': {'speed': 12.5}})
    (folder/'frame.json').write_text(json.dumps(model_meta))
    np.savez(folder/'model_input.npz', **{name:image for name in CAMERAS})
    subprocess.run([sys.executable,str(checker),str(capture.run)],check=True)
    model_meta['input_scalars'] = {}
    (folder/'frame.json').write_text(json.dumps(model_meta))
    result = subprocess.run([sys.executable,str(checker),str(capture.run)],capture_output=True,text=True)
    assert result.returncode != 0 and 'coverage mismatch' in result.stderr
    model_meta['input_scalars'] = {'SPEED': {'speed': 12.5}}
    (folder/'frame.json').write_text(json.dumps(model_meta))
    np.savez(folder/'model_input.npz', **{name:image for name in CAMERAS if name != 'CAM_FRONT'})
    result = subprocess.run([sys.executable,str(checker),str(capture.run)],capture_output=True,text=True)
    assert result.returncode != 0 and 'coverage mismatch' in result.stderr
    (folder/'frame.json').write_text(json.dumps(meta))
    (capture.run/'manifest.json').write_text(json.dumps(manifest))
    run_path=capture.run
    capture.request=lambda:{'recording':True,'id':'record','every':1,'max_frames':1 if limit_reason=='frame_limit' else 2000}
    if limit_reason == 'storage_limit': capture.bytes = 20*1024**3
    import shutil
    original_disk_usage = shutil.disk_usage
    from carla_safety_agent.sensor_capture import check_capture_quota as original_quota_check
    if limit_reason in ('capture_quota','quota_unknown'):
        monkeypatch.setattr('carla_safety_agent.sensor_capture.check_capture_quota',
                            lambda root,reserve,**kwargs:(limit_reason,'Quota admission stopped'))
    if limit_reason == 'disk_reserve':
        monkeypatch.setattr('carla_safety_agent.sensor_capture.shutil.disk_usage',
                            lambda _:SimpleNamespace(free=1024**3))
    preserved = (folder/'sensor_input.npz').read_bytes()
    capture.samples={name:{13:value} for name,value in samples.items()}
    capture.process_frame(13,SimpleNamespace(steer=0,throttle=0,brake=1))
    assert capture.run is None and capture.stop_reason==limit_reason
    assert (folder/'sensor_input.npz').read_bytes() == preserved
    assert not (run_path/'samples'/'0000000013').exists()
    bounded_manifest=json.loads((run_path/'manifest.json').read_text())
    assert bounded_manifest['status']=='saved_limit' and bounded_manifest['frame_count']==1
    assert bounded_manifest['stop_reason'] == limit_reason
    if limit_reason == 'disk_reserve': assert '1 GiB free disk reserve' in capture.error
    monkeypatch.setattr('carla_safety_agent.sensor_capture.shutil.disk_usage', original_disk_usage)
    monkeypatch.setattr('carla_safety_agent.sensor_capture.check_capture_quota', original_quota_check)
    capture.run=run_path  # Continue corruption tests against the committed sample.
    # The validator must reject a raw archive missing a camera, even if its PNG exists.
    with np.load(folder/'sensor_input.npz') as archive:
        arrays = {name:archive[name] for name in archive.files if name != 'CAM_FRONT'}
    np.savez(folder/'sensor_input.npz',**arrays)
    result = subprocess.run([sys.executable,str(checker),str(capture.run)],capture_output=True,text=True)
    assert result.returncode != 0 and 'Missing raw input arrays' in result.stderr
    arrays['CAM_FRONT']=image
    np.savez(folder/'sensor_input.npz',**arrays)
    specs=json.loads((capture.run/'calibration.json').read_text())
    specs['CAM_FRONT'].update(sensor_to_ego=np.eye(4).tolist(),ego_to_sensor=np.zeros((4,4)).tolist())
    (capture.run/'calibration.json').write_text(json.dumps(specs))
    result=subprocess.run([sys.executable,str(checker),str(capture.run)],capture_output=True,text=True)
    assert result.returncode != 0 and 'Extrinsics are not inverse' in result.stderr
    # New model recording with original four-view names must trigger capture,
    # independently of the auxiliary six CAM_* views.
    capture.source = 'model-input'
    capture.run = None
    names = ('rgb_front', 'rgb_left', 'rgb_right', 'rgb_back')
    capture.specs.update({name: {'type': 'sensor.camera.rgb','width':2,'height':2} for name in names})
    capture.request = lambda: {'recording': True, 'id': 'four-view-model', 'every': 1, 'max_frames': 2}
    capture.process({name: (13, image.copy()) for name in names},
                    SimpleNamespace(step=32), SimpleNamespace(steer=0, throttle=0, brake=1))
    assert capture.count == 1
    model_folder = capture.run/'samples'/'0000000013'
    model_frame = json.loads((model_folder/'frame.json').read_text())
    assert model_frame['actual_model_inputs'] == list(names)
    with np.load(model_folder/'model_input.npz') as archive:
        assert set(archive.files) == set(names)
        np.testing.assert_array_equal(archive['rgb_front'], image)
    from PIL import Image
    for name in names:
        np.testing.assert_array_equal(np.asarray(Image.open(model_folder/(name+'.png'))), image[:,:,:3][:,:,::-1])
        assert name in model_frame['available']
    # Fail a real next-sample write after admission, preserving one valid frame.
    import errno
    from carla_safety_agent.capture_recovery import recover_capture, inventory
    model_run = capture.run
    committed = (model_folder/'model_input.npz').read_bytes()
    capture.samples = {name:{14:value} for name,value in samples.items()}
    capture.world.get_snapshot = lambda:SimpleNamespace(frame=14,timestamp=SimpleNamespace(elapsed_seconds=.7))
    def full_disk(path, **arrays):
        Path(path).write_bytes(b'partial archive')
        raise OSError(errno.ENOSPC, 'injected disk full during NPZ write')
    original_save = Image.Image.save
    import carla_safety_agent.sensor_capture as capture_module
    original_json = capture_module.atomic_json
    def failed_metadata(path, value):
        if Path(path) == model_run/(write_failure+'.json'):
            raise OSError(errno.ENOSPC,'injected disk full during metadata write')
        return original_json(path,value)
    def failed_png(image_self, path, *args, **kwargs):
        if Path(path).suffix == '.png' and Path(path).parent.name == '0000000014':
            Path(path).write_bytes(b'partial png')
            raise OSError(errno.ENOSPC,'injected disk full during PNG write')
        return original_save(image_self,path,*args,**kwargs)
    with monkeypatch.context() as injection:
        if write_failure == 'npz': injection.setattr('carla_safety_agent.sensor_capture.np.savez', full_disk)
        elif write_failure == 'png': injection.setattr(Image.Image,'save',failed_png)
        else: injection.setattr(capture_module,'atomic_json',failed_metadata)
        with pytest.raises(OSError, match='injected disk full'):
            capture.process({name:(14,image.copy()) for name in names},
                            SimpleNamespace(step=33),SimpleNamespace(steer=0,throttle=0,brake=1))
    metadata_failure = write_failure in ('index','manifest')
    expected_count = 2 if metadata_failure else 1
    assert capture.count == expected_count and len(capture.frame_index) == expected_count
    assert (model_run/'samples/0000000014/frame.json').exists() == metadata_failure
    if write_failure == 'png':
        with np.load(model_run/'samples/0000000014/model_input.npz') as raw:
            assert set(raw.files) == set(names)
        assert any(p.read_bytes() == b'partial png' for p in (model_run/'samples/0000000014').glob('*.png'))
    assert (model_folder/'model_input.npz').read_bytes() == committed
    capture.sensors = []
    if metadata_failure:
        # Disk stays unavailable through finalization: close must report failure.
        with monkeypatch.context() as injection:
            injection.setattr(capture_module,'atomic_json',failed_metadata)
            assert any('Manifest finalization' in error for error in capture.close())
    else:
        assert capture.close() == []
    failed_manifest = json.loads((model_run/'manifest.json').read_text())
    assert failed_manifest['status'] == ('recording' if write_failure=='manifest' else 'saved_capture_error')
    if write_failure != 'manifest': assert failed_manifest['stop_reason'] == 'capture_io_error'
    assert len(json.loads((model_run/'index.json').read_text())['frames']) == 1
    before = inventory(model_run)
    # Use the actual raw-data validator, not a mocked audit result.
    recovered = recover_capture(model_run,model_run.parent,checker,sys.executable,lambda:None)
    assert inventory(model_run) == before
    recovered_manifest = json.loads((recovered/'manifest.json').read_text())
    assert recovered_manifest['status'] == 'saved_recovered'
    assert recovered_manifest['frame_count'] == expected_count
    assert recovered_manifest['recovery']['omitted_uncommitted_tail'] == ([] if metadata_failure else ['0000000014'])
    assert (recovered/'samples/0000000013/model_input.npz').read_bytes() == committed
