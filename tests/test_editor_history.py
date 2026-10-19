import json
import pytest
from carla_safety_agent.editor_history import editor_history
from carla_safety_agent.transform_history import TransformHistory
from carla_safety_agent.deletion_history import DeletionHistory

IDENTITY = {'episode':'1','actor_id':7,'type_id':'static.prop.test','stable_id':'stable-a'}
def pose(x):
    return {'location':{'x':x,'y':0,'z':0},'rotation':{'pitch':0,'yaw':0,'roll':0}}

def test_actor_material_journal_and_corrupt_entry(tmp_path):
    from types import SimpleNamespace
    from carla_safety_agent.actor_material_history import ActorMaterialHistory,apply_with_history
    journal=ActorMaterialHistory(tmp_path/'actors')
    identity=dict(episode='1',actor_id=2,stable_id='abc',blueprint_id='vehicle.audi.a2',component='VehicleMesh',slot=4)
    operation=apply_with_history(journal.root,identity,None,'a'*64,SimpleNamespace(apply=lambda:None))
    (journal.root/'broken.json').write_text('{}')
    before={p.name:p.read_bytes() for p in journal.root.glob('*.json')}
    result=editor_history(TransformHistory(tmp_path/'t'),DeletionHistory(tmp_path/'d'),actor_materials=journal)
    assert result['entries'][0]['operation_id']==operation
    assert result['entries'][0]['kind']=='actor-material'
    assert result['entries'][0]['undo_supported'] is False
    assert result['capabilities']['actor_material_transition'] is True
    assert not result['complete'] and len(result['warnings'])==1
    assert before=={p.name:p.read_bytes() for p in journal.root.glob('*.json')}

def test_combines_real_journals_without_mutation(tmp_path):
    t, d = TransformHistory(tmp_path/'t'), DeletionHistory(tmp_path/'d')
    row = t.begin(IDENTITY,'record',pose(0),pose(1))
    row = t.finish(IDENTITY,row['pending']['id'],pose(1))
    undo = t.begin(IDENTITY,'undo',pose(1),expected_revision=row['revision'])
    t.finish(IDENTITY,undo['pending']['id'],pose(0))
    deletion = d.begin(1,7,'static.prop.test',dict(scene_id='scene-a',version='v1',stable_id='stable-a'))
    d.finish(deletion)
    before = {str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    result = editor_history(t,d)
    assert result['complete'] and result['total']==2
    assert [r['kind'] for r in result['entries']]==['delete','transform']
    assert result['entries'][1]['state']=='undone'
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    assert editor_history(t,d,1)['truncated']

def test_pending_and_corrupt_journals_are_visible(tmp_path):
    t, d = TransformHistory(tmp_path/'t'), DeletionHistory(tmp_path/'d')
    t.begin(IDENTITY,'record',pose(0),pose(1))
    bad = t.root/'wrong'; bad.mkdir()
    (bad/'current.json').write_text(json.dumps({'identity':IDENTITY}))
    result = editor_history(t,d)
    assert not result['complete'] and len(result['warnings'])==1
    assert result['entries'][0]['kind']=='transform-intent'
    assert result['entries'][0]['created_at'] is None
    assert result['entries'][0]['state']=='attempting'

@pytest.mark.parametrize('limit',[True,0,201,1.5,'50'])
def test_invalid_limit(tmp_path,limit):
    with pytest.raises(ValueError):
        editor_history(TransformHistory(tmp_path/'t'),DeletionHistory(tmp_path/'d'),limit)

def test_linked_store_refused(tmp_path):
    target=tmp_path/'target'; target.mkdir()
    link=tmp_path/'link'; link.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='Linked'):
        editor_history(TransformHistory(link),DeletionHistory(tmp_path/'d'))


def test_material_history_is_read_only_and_preserves_large_environment_id(tmp_path):
    from carla_safety_agent.material_history import MaterialHistory
    materials=MaterialHistory(tmp_path/'materials')
    identity=dict(episode='1',object_id='18446744073709551615',target='house',component='mesh',slot=2)
    operation=materials.execute(identity,'a'*64,None,lambda:None)
    before=materials.path(operation).read_bytes()
    result=editor_history(TransformHistory(tmp_path/'t'),DeletionHistory(tmp_path/'d'),materials=materials)
    assert result['complete'] and result['total']==1
    assert result['entries'][0]['identity']==identity
    assert materials.path(operation).read_bytes()==before
