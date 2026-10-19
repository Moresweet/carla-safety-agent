import json
import zipfile
import pytest
from carla_safety_agent.capture_excerpt import create_excerpt,select_window


def fixture(tmp_path):
    source=tmp_path/'capture-test';source.mkdir()
    entries=[{'frame':10+i,'timestamp':1+i*.1,'path':f'samples/{10+i:010d}'} for i in range(5)]
    manifest={'schema_version':'carla-safety-dataset/0.2','run_id':source.name,'status':'saved','frame_count':5,
        'sampling_every_frames':1,'input_archive':'sensor_input.npz','execution_id':'execution',
        'files':{'calibration':'calibration.json','index':'index.json'},'sensors':{'CAM_FRONT':{'samples':5}}}
    (source/'manifest.json').write_text(json.dumps(manifest));(source/'index.json').write_text(json.dumps({'frames':entries}))
    (source/'calibration.json').write_text('{}')
    for entry in entries:
        folder=source/entry['path'];folder.mkdir(parents=True)
        (folder/'frame.json').write_text(json.dumps(entry));(folder/'sensor_input.npz').write_bytes(b'raw-fixture')
    return source,entries,manifest


def test_window_selection_is_timestamp_based_and_never_interpolates(tmp_path):
    _,entries,manifest=fixture(tmp_path)
    selected,window=select_window(entries,manifest,12,.1,.1)
    assert [row['frame'] for row in selected]==[11,12,13]
    assert not window['clipped_before'] and not window['clipped_after']
    selected,window=select_window(entries,manifest,10,2,0)
    assert len(selected)==1 and window['clipped_before']
    for args in [(True,1,1),(999,1,1),(12,-1,1),(12,True,1),(12,1,float('nan'))]:
        with pytest.raises(ValueError):select_window(entries,manifest,*args)


def test_excerpt_carries_verified_map_source_into_zip(tmp_path,monkeypatch):
    from types import SimpleNamespace as NS
    from carla_safety_agent.map_projection_archive import archive_map_projection,read_map_projection
    source,_,manifest=fixture(tmp_path)
    xml='<OpenDRIVE><header><geoReference>+proj=tmerc</geoReference></header></OpenDRIVE>'
    ref=archive_map_projection(source,NS(name='Town04',to_opendrive=lambda:xml))
    manifest['map_projection']=ref;manifest['files']['map_projection']=ref['path']
    (source/'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr('carla_safety_agent.capture_excerpt.audit_capture',lambda *_:{'state':'passed'})
    dataset,bundle,_=create_excerpt(source,tmp_path/'output',12,.1,.1,'validator','python',lambda:None)
    assert read_map_projection(dataset,ref)==xml
    with zipfile.ZipFile(bundle) as archive:
        assert archive.read(dataset.name+'/'+ref['path']).decode()==xml


def test_audited_copy_zip_and_original_metadata_preserved(tmp_path,monkeypatch):
    source,_,_=fixture(tmp_path);original={str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}
    calls=[]
    monkeypatch.setattr('carla_safety_agent.capture_excerpt.audit_capture',lambda *_:{'state':'passed','scope':'fixture, not native sensor verification'})
    dataset,bundle,report=create_excerpt(source,tmp_path/'output',12,.1,.1,'validator','python',lambda:calls.append('inactive'))
    manifest=json.loads((dataset/'manifest.json').read_text())
    assert manifest['status']=='saved_excerpt' and manifest['frame_count']==3 and manifest['sensors']['CAM_FRONT']['samples']==3
    assert manifest['excerpt']['source_run_id']==source.name
    assert [p.name for p in sorted((dataset/'samples').iterdir())]==['0000000011','0000000012','0000000013']
    assert report['source_unchanged'] and report['raw_data_verified'] and len(calls)==2
    with zipfile.ZipFile(bundle) as archive:
        assert archive.read('source-metadata/manifest.json')==original['manifest.json']
        assert archive.read(dataset.name+'/samples/0000000012/sensor_input.npz')==b'raw-fixture'
    assert {str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}==original


@pytest.mark.parametrize('fault',['audit','source_mutation','active','link','unexpected_file'])
def test_incomplete_or_untrusted_excerpt_is_not_published(tmp_path,monkeypatch,fault):
    source,_,_=fixture(tmp_path)
    def audit(*_):
        if fault=='source_mutation':(source/'samples/0000000012/sensor_input.npz').write_bytes(b'changed')
        return {'state':'failed' if fault=='audit' else 'passed'}
    monkeypatch.setattr('carla_safety_agent.capture_excerpt.audit_capture',audit)
    def inactive():
        if fault=='active':raise ValueError('worker alive')
    if fault=='link':
        raw=source/'samples/0000000012/sensor_input.npz';raw.unlink();raw.symlink_to(source/'calibration.json')
    if fault=='unexpected_file':(source/'samples/0000000012/secret.env').write_text('fixture')
    output=tmp_path/'output'
    with pytest.raises(ValueError):create_excerpt(source,output,12,0,0,'validator','python',inactive)
    assert not (output/'excerpt.zip').exists()
    if (output/'report.json').exists():assert json.loads((output/'report.json').read_text())['state']=='failed'


def test_sparse_editor_boundaries_and_collision_window(tmp_path,monkeypatch):
    from carla_safety_agent.editor_events import editor_events
    from carla_safety_agent.replay import replay_editor_events,recorded_collisions
    source,entries,manifest=fixture(tmp_path)
    # A command between sparse samples must follow its first later saved frame.
    for i,entry in reversed(list(enumerate(entries))):
        previous=source/entry['path'];entry['frame']=10+i*10;entry['path']=f"samples/{entry['frame']:010d}"
        previous.rename(source/entry['path'])
    records=[{'execution_id':'execution','command_id':str(before),'state':'responded',
              'observed_frame_before':before,'observed_frame_after':before,'response':{'ok':True}}
             for before in (5,15,35)]
    commands={'schema_version':'carla-editor-events/1','execution_id':'execution','records':records,
              'events':editor_events(records,[e['frame'] for e in entries],'execution')}
    collisions={'schema_version':'carla-collision-events/1','source':'sensor.other.collision',
        'buffer_dropped_since_sensor_start':2,'invalid_observations_since_sensor_start':0,
        'events':[{'kind':'collision','frame':f,'timestamp':t,'other_actor_id':1,'other_actor_type':'fixture',
            'normal_impulse':{'x':1,'y':0,'z':0}} for f,t in ((10,1),(20,1.1),(40,1.3))]}
    manifest['sampling_every_frames']=10
    manifest['files'].update(editor_events='editor-events.json',collisions='collisions.json')
    for name,value in [('manifest.json',manifest),('index.json',{'frames':entries}),('editor-events.json',commands),('collisions.json',collisions)]:
        (source/name).write_text(json.dumps(value))
    monkeypatch.setattr('carla_safety_agent.capture_excerpt.audit_capture',lambda *_:{'state':'passed'})
    dataset,bundle,_=create_excerpt(source,tmp_path/'output',20,0,0,'validator','python',lambda:None)
    events=replay_editor_events(dataset.parent,dataset.name)['events']
    assert len(events)==1 and events[0]['command_id']=='15' and events[0]['seek_frame']==20
    found=recorded_collisions(dataset,[entries[1]])
    assert len(found['events'])==1 and found['events'][0]['frame']==20
    with zipfile.ZipFile(bundle) as archive:
        assert len(json.loads(archive.read('source-metadata/collisions.json'))['events'])==3
