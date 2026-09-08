import json
from types import SimpleNamespace
import numpy as np
import pytest
from carla_safety_agent.sensor_capture import depth_meters, bev_preview, calibration
from carla_safety_agent.provenance import ActorProvenance
from carla_safety_agent.replay import replay_file, replay_index
from carla_safety_agent.uv_audit import audit_uv
from carla_safety_agent.sensor_capture import SensorCapture, CAMERAS


def test_depth_channel_order_and_units():
    values = np.array([[[0,0,0,255], [255,255,255,255], [0,0,1,255]]], dtype=np.uint8)
    meters = depth_meters(values)
    assert meters.dtype == np.float32
    assert meters[0,0] == 0
    assert meters[0,1] == pytest.approx(1000)
    assert meters[0,2] == pytest.approx(1000/16777215)


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
    assert restored.origin(2,actor) == 'existing'
    assert restored.origin(1,SimpleNamespace(id=12,type_id='walker.test')) == 'existing'


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


def test_standalone_capture_records_real_rig_arrays_without_model_claim(tmp_path, monkeypatch):
    import threading
    capture = object.__new__(SensorCapture)
    capture.source = 'sensor-rig'
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
    capture.world = SimpleNamespace(get_snapshot=lambda:SimpleNamespace(timestamp=SimpleNamespace(elapsed_seconds=.6)),
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
