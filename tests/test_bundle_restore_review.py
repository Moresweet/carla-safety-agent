from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from carla_safety_agent.bundle_restore_review import RestoreReviews
from test_studio_bridge import functions


def fixture():
    selection={'bundle_id':'bundle','scene_id':'scene','version':'version'}
    baseline={'map':'Town04','objects':[],'weather':{'wetness':0}}
    target={'map':'Town04','objects':[{'stable_id':'new'}],'environment_materials':[]}
    manifest={'files':{'scene':'hash'}}
    return selection,baseline,target,manifest


def test_review_is_readonly_explicit_single_use_and_uint64_safe():
    selection,baseline,target,manifest=fixture();reviews=RestoreReviews()
    review=reviews.issue(selection,manifest,target,baseline,2**64-1)
    assert review['episode']==str(2**64-1)
    assert review['create_count']==1 and review['material_state_replaced']
    assert not review['live_world_modified'] and not review['dependency_preflight_completed']
    for payload in ({'review_token':review['review_token'],'confirmed':1},{'review_token':review['review_token']}):
        with pytest.raises(ValueError):reviews.consume(payload,manifest,baseline,2**64-1)
    data={'review_token':review['review_token'],'confirmed':True}
    assert reviews.consume(data,manifest,baseline,2**64-1)==selection
    with pytest.raises(ValueError):reviews.consume(data,manifest,baseline,2**64-1)


@pytest.mark.parametrize('change',['world','package','weather','object','expired'])
def test_changed_review_refuses_and_invalidates_approval(change):
    selection,baseline,target,manifest=fixture();now=[0];reviews=RestoreReviews(lambda:now[0])
    review=reviews.issue(selection,manifest,target,baseline,10)
    episode=10
    if change=='world':episode=11
    if change=='package':manifest['files']['scene']='newhash'
    if change=='weather':baseline['weather']['wetness']=1
    if change=='object':baseline['objects']=[{'stable_id':'later'}]
    if change=='expired':now[0]=121
    data={'review_token':review['review_token'],'confirmed':True}
    with pytest.raises(ValueError):reviews.consume(data,manifest,baseline,episode)
    with pytest.raises(ValueError):reviews.selection(review['review_token'])


def test_review_same_world_order_independent_but_cross_map_rejected():
    selection,baseline,target,manifest=fixture();reviews=RestoreReviews()
    baseline['objects']=[{'stable_id':'a'},{'stable_id':'b'}]
    target['objects']=[{'stable_id':'a'},{'stable_id':'new'}]
    review=reviews.issue(selection,manifest,target,baseline,10)
    assert (review['update_count'],review['create_count'],review['preserved_user_objects'])==(1,1,1)
    baseline['objects'].reverse()
    reviews.consume({'review_token':review['review_token'],'confirmed':True},manifest,baseline,10)
    target['map']='Town05'
    with pytest.raises(ValueError,match='another map'):reviews.issue(selection,manifest,target,baseline,10)


def test_bridge_saves_baseline_before_mutation_and_does_not_retry_failure():
    selection,baseline,target,manifest=fixture();reviews=RestoreReviews()
    review=reviews.issue(selection,manifest,target,baseline,10)
    saved={'head':{'scene_id':'scene'},'document':target};calls=[]
    def backup(document,name):
        calls.append(('backup',deepcopy(document)))
        return {'head':{'scene_id':'backup','version':'v1'}}
    def restore(document):calls.append(('restore',document));raise RuntimeError('native failure')
    env=functions('confirm_bundle_restore',connect_world=lambda:NS(id=10),
        BUNDLE_RESTORE_REVIEWS=reviews,BUNDLES=NS(scene_snapshot=lambda _: (manifest,{},saved)),
        capture_scene_document=lambda:baseline,SCENES=NS(save=backup),restore_scene_document=restore)
    data={'review_token':review['review_token'],'confirmed':True}
    with pytest.raises(RuntimeError,match='baseline scene backup version v1'):env['confirm_bundle_restore'](data)
    assert [call[0] for call in calls]==['backup','restore']
    with pytest.raises(ValueError):env['confirm_bundle_restore'](data)
    assert len(calls)==2


def test_backup_failure_prevents_world_mutation():
    selection,baseline,target,manifest=fixture();reviews=RestoreReviews()
    review=reviews.issue(selection,manifest,target,baseline,10)
    def fail(*_):raise OSError('disk full')
    env=functions('confirm_bundle_restore',connect_world=lambda:NS(id=10),
        BUNDLE_RESTORE_REVIEWS=reviews,BUNDLES=NS(scene_snapshot=lambda _: (manifest,{},{})),
        capture_scene_document=lambda:baseline,SCENES=NS(save=fail),
        restore_scene_document=lambda _:pytest.fail('mutation after backup failure'))
    with pytest.raises(OSError):env['confirm_bundle_restore']({'review_token':review['review_token'],'confirmed':True})


def test_busy_world_refuses_confirmation_before_read_or_backup():
    def busy():raise RuntimeError('active execution')
    env=functions('confirm_bundle_restore',connect_world=busy)
    with pytest.raises(RuntimeError,match='active execution'):
        env['confirm_bundle_restore']({'review_token':'x','confirmed':True})
