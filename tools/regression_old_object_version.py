"""Restore a missing actor from an old version without moving the head cursor."""
import json
import uuid
from urllib.error import HTTPError
from regression_scene_versions import ROOT, request
from cleanup_superseded_model_captures import idle
from carla_safety_agent.scene_store import SceneStore


def main():
    idle()
    assert request('system/preflight')['ready']
    owned = set()
    report = {'passed': False}
    output = ROOT/'runs/validation'/('old-object-version-'+uuid.uuid4().hex+'.json')
    try:
        before = request('scenes/save', {'name':'旧版本恢复测试前'})['document']
        previous = {obj['stable_id'] for obj in before['objects']}
        prop = request('objects/spawn', {'blueprint_id':'static.prop.advertisement',
            'transform':{'location':{'x':393.098,'y':-228.088,'z':2.5}}})['object']
        owned.add(prop['id'])
        first = request('scenes/save', {'name':'验收：单对象历史版本选择'})
        target = next(obj for obj in first['document']['objects'] if obj['stable_id'] not in previous)
        stable = target['stable_id']
        request('objects/update', {'actor_id':prop['id'],'transform':{'location':{'x':403.098}}})
        second = request('scenes/save', {'name':first['head']['name'],
            'scene_id':first['head']['scene_id'],'expected_version':first['head']['version']})
        second_target = next(obj for obj in second['document']['objects'] if obj['stable_id']==stable)
        assert abs(second_target['transform']['location']['x']-target['transform']['location']['x'])>9
        request('objects/delete', {'actor_id':prop['id']})
        owned.remove(prop['id'])
        selection = {'scene_id':first['head']['scene_id'],'version':first['head']['version'],
                     'stable_id':stable,'confirmed':True}
        restored = request('objects/restore-missing', selection)
        actor = restored['bindings'][stable]
        owned.add(actor)
        current = request('scenes/save', {'name':'旧版本单对象恢复结果'})['document']
        assert next(obj for obj in current['objects'] if obj['stable_id']==stable)==target
        store = SceneStore(ROOT/'data/scenes')
        assert store.read(selection['scene_id'])['head']==second['head']
        try:
            request('objects/restore-missing', selection)
        except HTTPError as error:
            detail=json.load(error)
            assert 'already exists' in detail.get('error','')
            report['duplicate_rejected'] = detail
        else:
            raise AssertionError('Repeated restore unexpectedly succeeded')
        after = request('scenes/save', {'name':'重复恢复拒绝后核对'})['document']
        assert after['objects']==current['objects']
        report.update(passed=True,selection=selection,head_preserved=second['head'],
                      restored_actor=actor,restored_object=target)
    finally:
        report['cleanup']=[]
        for actor in owned:
            try:report['cleanup'].append(request('objects/delete',{'actor_id':actor}))
            except Exception as error:
                report['passed']=False
                report['cleanup'].append({'actor_id':actor,'error':str(error)})
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'receipt':str(output),**report},ensure_ascii=False))


if __name__=='__main__':
    main()
