"""Live same-map deletion snapshot roundtrip using one owned temporary prop."""
import json
import uuid
import argparse

from regression_scene_versions import ROOT, request
from cleanup_superseded_model_captures import idle
from carla_safety_agent.scene_store import SceneStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--single-object', action='store_true')
    args = parser.parse_args()
    idle()
    assert request('system/preflight')['ready']
    output = ROOT / 'runs/validation' / ('delete-backup-' + uuid.uuid4().hex + '.json')
    report = {'passed': False, 'scope': 'same-map static prop deletion snapshot and restoration'}
    owned = set()
    try:
        sentinel = request('objects/spawn', {'blueprint_id': 'static.prop.advertisement',
            'transform': {'location': {'x': 413.098, 'y': -228.088, 'z': 2.5}}})['object']
        owned.add(sentinel['id'])
        report['sentinel_actor'] = sentinel['id']
        before = request('scenes/save', {'name': '删除快照验收：原工作台'})['document']
        original = {item['stable_id']: item for item in before['objects']}
        assert original, 'Must test preservation of at least one other object'
        prop = request('objects/spawn', {'blueprint_id': 'static.prop.advertisement',
            'transform': {'location': {'x': 393.098, 'y': -228.088, 'z': 2.5}}})['object']
        owned.add(prop['id'])
        report['actor_before'] = prop['id']
        deletion = request('objects/delete', {'actor_id': prop['id']})
        assert deletion['ok'] is True
        owned.remove(prop['id'])
        report['deletion'] = deletion
        head = deletion['backup']
        from carla_safety_agent.scene_store import identifier, read_json
        operation_id = identifier(deletion['operation_id'])
        journal = read_json(ROOT / 'data/deletion-history' / (operation_id + '.json'))
        assert journal['operation_id'] == operation_id and journal['state'] == 'confirmed'
        assert journal['actor_id'] == prop['id'] and journal['type_id'] == 'static.prop.advertisement'
        assert journal['backup'] == {key:head[key] for key in ('scene_id','version','stable_id')}
        report['deletion_journal'] = journal
        missing = request('objects/deletion-inspection?operation_id=' + operation_id)
        assert missing['observation'] == 'missing' and missing['actor_id'] is None
        assert missing['same_map'] is True and missing['same_episode'] is True
        report['inspection_missing'] = missing
        saved = SceneStore(ROOT / 'data/scenes').read(head['scene_id'], head['version'])
        added = [item for item in saved['document']['objects'] if item['stable_id'] not in original]
        assert len(added) == 1 and added[0]['blueprint_id'] == 'static.prop.advertisement'
        stable = added[0]['stable_id']
        deleted_state = request('scenes/save', {'name': '删除快照验收：删除已确认'})['document']
        assert stable not in {item['stable_id'] for item in deleted_state['objects']}
        if args.single_object:
            request('objects/update', {'actor_id': sentinel['id'],
                'transform': {'location': {'x': 423.098}}})
            changed = request('scenes/save', {'name': '单对象恢复验收：保留旁边的新修改'})['document']
            original = {item['stable_id']: item for item in changed['objects']}
            restored = request('objects/restore-missing', {'scene_id': head['scene_id'],
                'version': head['version'], 'stable_id': stable, 'confirmed': True})
            report['scope'] = 'single missing object restore preserving subsequent edits to another object'
        else:
            restored = request('scenes/restore', {'scene_id': head['scene_id'], 'version': head['version']})
        actor_id = restored['bindings'][stable]
        owned.add(actor_id)
        assert actor_id != prop['id']
        present = request('objects/deletion-inspection?operation_id=' + operation_id)
        assert present['observation'] == 'present' and present['actor_id'] == actor_id
        assert read_json(ROOT / 'data/deletion-history' / (operation_id + '.json')) == journal
        report['inspection_present'] = present
        after = request('scenes/save', {'name': '删除快照验收：恢复已确认'})['document']
        objects = {item['stable_id']: item for item in after['objects']}
        assert objects[stable] == added[0]
        assert {key: objects[key] for key in original} == original
        assert set(objects) == set(original) | {stable}
        report.update(passed=True, stable_id=stable, actor_after=actor_id,
                      original_objects_unchanged=True, backup_head=head)
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        report['cleanup'] = []
        for actor_id in owned:
            try:
                report['cleanup'].append(request('objects/delete', {'actor_id': actor_id}))
            except Exception as error:
                report['cleanup'].append({'actor_id': actor_id, 'error': str(error)})
                report['passed'] = False
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({'receipt': str(output), **report}, ensure_ascii=False))


if __name__ == '__main__':
    main()
