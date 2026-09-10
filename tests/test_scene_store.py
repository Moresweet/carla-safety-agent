import json

import pytest
from carla_safety_agent.scene_store import SceneStore, validate_scene


def document(x=1):
    return {'map':'Town04', 'objects':[{'stable_id':'stable', 'blueprint_id':'static.prop.box01',
        'transform':{'location':{'x':x,'y':0,'z':1},'rotation':{'pitch':0,'yaw':0,'roll':0}}}]}


def test_history_conflicts_and_restart(tmp_path):
    store = SceneStore(tmp_path)
    first = store.save(document(), 'scene')['head']
    with pytest.raises(ValueError): store.save(document(), 'scene', first['scene_id'])
    second = store.save(document(2), 'scene', first['scene_id'], first['version'])['head']
    undo = store.move(first['scene_id'], -1, second['version'])
    assert undo['document']['objects'][0]['transform']['location']['x'] == 1
    assert SceneStore(tmp_path).read(first['scene_id'])['head']['version'] == first['version']
    assert store.move(first['scene_id'], 1, first['version'])['head']['version'] == second['version']


@pytest.mark.parametrize('bad', ['../escape','/tmp/escape','a/b',''])
def test_paths_confined(tmp_path, bad):
    with pytest.raises(ValueError): SceneStore(tmp_path).read(bad)


def test_validation_and_branch_keep_old_versions(tmp_path):
    with pytest.raises(ValueError): validate_scene(document(float('nan')))
    store = SceneStore(tmp_path)
    first = store.save(document(), 'first')['head']
    second = store.save(document(2), 'second', first['scene_id'], first['version'])['head']
    store.move(first['scene_id'], -1, second['version'])
    branch = store.save(document(3), 'branch', first['scene_id'], first['version'])['head']
    assert second['version'] not in branch['history']
    assert store.read(first['scene_id'], second['version'])['document']['name'] == 'second'


@pytest.mark.parametrize('field,value', [('weather',{'wetness':True}), ('weather',[]),
    ('weather',{'wetness':float('inf')}), ('spectator',{'location':{}}),
    ('schema_version','carla-scene/999')])
def test_full_scene_preflight_rejects_malformed_metadata(field, value):
    scene = document()
    scene[field] = value
    with pytest.raises(ValueError): validate_scene(scene)


@pytest.mark.parametrize('options', [{'scale':0}, {'scale':True}, {'mass':-1}, {'arbitrary':'value'}])
def test_spawn_options_are_checked_before_restore(options):
    scene = document()
    scene['objects'][0]['spawn_options'] = options
    with pytest.raises(ValueError): validate_scene(scene)


def test_empty_scene_normalizes_objects():
    assert validate_scene({'map':'Town04'})['objects'] == []


@pytest.mark.parametrize('corruption', ['transform', 'weather', 'schema'])
def test_corrupted_history_does_not_advance_cursor(tmp_path, corruption):
    store = SceneStore(tmp_path)
    first = store.save(document(), 'first')['head']
    second = store.save(document(2), 'second', first['scene_id'], first['version'])['head']
    folder = tmp_path / first['scene_id']
    version_file = folder / (first['version'] + '.json')
    damaged = json.loads(version_file.read_text())
    if corruption == 'transform':
        damaged['objects'][0]['transform']['location'] = {'x': 1}
    elif corruption == 'weather':
        damaged['weather'] = {'wetness': True}
    else:
        damaged['schema_version'] = 'carla-scene/999'
    version_file.write_text(json.dumps(damaged))
    previous_head = (folder / 'head.json').read_bytes()
    with pytest.raises(ValueError):
        store.move(first['scene_id'], -1, second['version'])
    assert (folder / 'head.json').read_bytes() == previous_head
    with pytest.raises(ValueError):
        store.read(first['scene_id'], first['version'])
    assert store.read(first['scene_id'])['document']['version'] == second['version']


@pytest.mark.parametrize('defect',['scene_id','version','cursor','duplicate_history','bool_cursor','nan','duplicate_key'])
def test_invalid_head_is_preserved_and_cannot_be_extended(tmp_path,defect):
    store=SceneStore(tmp_path);saved=store.save(document(),'scene');head=saved['head']
    path=tmp_path/head['scene_id']/'head.json';damaged=json.loads(path.read_text())
    if defect=='scene_id':damaged['scene_id']='other'
    if defect=='version':damaged['version']='other'
    if defect=='cursor':damaged['cursor']=100
    if defect=='duplicate_history':damaged['history']*=2
    if defect=='bool_cursor':damaged['cursor']=False
    if defect=='nan':damaged['updated_at']=float('nan')
    raw=json.dumps(damaged)
    if defect=='duplicate_key':raw=raw[:-1]+',"version":"other"}'
    path.write_text(raw);before=path.read_bytes()
    for operation in (lambda:store.read(head['scene_id']),
                      lambda:store.save(document(),'new',head['scene_id'],head['version']),
                      lambda:store.move(head['scene_id'],-1,head['version'])):
        with pytest.raises(ValueError):operation()
        assert path.read_bytes()==before


@pytest.mark.parametrize('field',['scene_id','version','name','saved_at'])
def test_document_identity_and_metadata_checked_before_history_move(tmp_path,field):
    store=SceneStore(tmp_path);first=store.save(document(),'first')['head']
    second=store.save(document(2),'second',first['scene_id'],first['version'])['head']
    folder=tmp_path/first['scene_id'];path=folder/(first['version']+'.json')
    value=json.loads(path.read_text());value[field]=None;path.write_text(json.dumps(value))
    before=(folder/'head.json').read_bytes()
    with pytest.raises(ValueError):store.read(first['scene_id'],first['version'])
    with pytest.raises(ValueError):store.move(first['scene_id'],-1,second['version'])
    assert (folder/'head.json').read_bytes()==before


@pytest.mark.parametrize('target',['directory','head','version','lock'])
def test_scene_symlinks_rejected_without_touching_targets(tmp_path,target):
    store=SceneStore(tmp_path/'scenes');saved=store.save(document(),'scene')['head']
    folder=store.root/saved['scene_id']
    if target=='directory':
        outside=tmp_path/'outside';folder.rename(outside);folder.symlink_to(outside,target_is_directory=True)
        protected=outside/'head.json'
    else:
        name={'head':'head.json','version':saved['version']+'.json','lock':'.lock'}[target]
        path=folder/name;outside=tmp_path/'outside';path.rename(outside);path.symlink_to(outside)
        protected=outside
    before=protected.read_bytes()
    with pytest.raises(ValueError):store.read(saved['scene_id'])
    assert protected.read_bytes()==before
    if target in ('directory','head','lock'):
        with pytest.raises(ValueError):store.save(document(),'new',saved['scene_id'],saved['version'])
        assert protected.read_bytes()==before


def test_atomic_fsync_failure_preserves_previous_file(tmp_path,monkeypatch):
    from carla_safety_agent.scene_store import atomic
    path=tmp_path/'head.json';path.write_text('previous')
    def fail(_):raise OSError('controlled flush failure')
    monkeypatch.setattr('carla_safety_agent.scene_store.os.fsync',fail)
    with pytest.raises(OSError,match='flush'):atomic(path,{'next':True})
    assert path.read_text()=='previous'


def test_directory_sync_failure_reports_already_published_state(tmp_path,monkeypatch):
    from carla_safety_agent.scene_store import atomic
    path=tmp_path/'state.json';calls=[]
    def sync(descriptor):
        calls.append(descriptor)
        if len(calls)==2:raise OSError('directory sync fault')
    monkeypatch.setattr('carla_safety_agent.scene_store.os.fsync',sync)
    with pytest.raises(OSError,match='was replaced'):atomic(path,{'published':True})
    assert json.loads(path.read_text())=={'published':True}


def test_failed_head_publish_keeps_old_cursor_and_new_version_for_inspection(tmp_path,monkeypatch):
    from carla_safety_agent import scene_store
    store=SceneStore(tmp_path);first=store.save(document(),'first')['head']
    original=scene_store.atomic
    def publish(path,payload):
        if path.name=='head.json':raise OSError('controlled head publish failure')
        original(path,payload)
    monkeypatch.setattr(scene_store,'atomic',publish)
    with pytest.raises(OSError):store.save(document(2),'second',first['scene_id'],first['version'])
    assert store.read(first['scene_id'])['head']==first
    assert len(list((tmp_path/first['scene_id']).glob('*.json')))==3


def test_oversized_scene_and_boolean_history_direction_rejected(tmp_path):
    store=SceneStore(tmp_path);first=store.save(document(),'first')['head']
    with pytest.raises(ValueError):store.move(first['scene_id'],True,first['version'])
    path=tmp_path/first['scene_id']/(first['version']+'.json')
    with path.open('wb') as stream:stream.truncate(16*1024*1024+1)
    with pytest.raises(ValueError,match='size'):store.read(first['scene_id'])


@pytest.mark.parametrize('field,value',[('name','other'),('map','Town05'),('object_count',0)])
def test_current_head_metadata_matches_version_before_read_or_append(tmp_path,field,value):
    store=SceneStore(tmp_path);head=store.save(document(),'scene')['head']
    path=tmp_path/head['scene_id']/'head.json';damaged=json.loads(path.read_text())
    damaged[field]=value;path.write_text(json.dumps(damaged));before=path.read_bytes()
    with pytest.raises(ValueError,match='differs'):store.read(head['scene_id'])
    with pytest.raises(ValueError,match='differs'):store.save(document(),'new',head['scene_id'],head['version'])
    assert path.read_bytes()==before
