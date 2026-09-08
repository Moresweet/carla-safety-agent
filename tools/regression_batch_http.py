"""Exercise live batch HTTP bookkeeping without dispatching a simulation."""
import json
import time
from urllib.error import HTTPError
from regression_scene_versions import ROOT, request


def main():
    before = request('session/status')['session']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    dimensions = {**{axis: [{'id': 'http-check', 'configuration': {}}]
                     for axis in ('scenes', 'models', 'weather', 'textures')}, 'seeds': [1]}
    created = request('batches/create', dimensions)
    assert created['ok'] and created['dispatched'] is False
    batch_id = created['batch_id']
    control = lambda action: request('batches/control', {'batch_id': batch_id, 'action': action})
    try:
        assert control('pause')['paused'] is True
        def paused_scheduler():
            started = request('batches/scheduler', {'batch_id': batch_id, 'action': 'start'})['scheduler']
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                status = request('batches/scheduler')['scheduler']
                assert status['scheduler_id'] == started['scheduler_id']
                if status['state'] != 'running':
                    assert status['state'] == 'paused'
                    return status
                time.sleep(.1)
            raise AssertionError('Paused queue scheduler did not finish')
        first_scheduler = paused_scheduler()
        second_scheduler = paused_scheduler()
        assert first_scheduler['scheduler_id'] != second_scheduler['scheduler_id']
        try:
            request('batches/scheduler', {'batch_id': batch_id, 'action': 'cancel',
                    'scheduler_id': first_scheduler['scheduler_id']})
        except HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError('Stale scheduler cancellation accepted')
        unchanged = request('batches/scheduler')['scheduler']
        assert unchanged['scheduler_id'] == second_scheduler['scheduler_id']
        assert not unchanged.get('cancel_requested')
        assert control('advance')['action'] == 'paused'
        report = request('batches/report?batch_id='+batch_id)['report']
        assert report['paused'] and report['state_counts'] == {'pending': 1}
        assert all(row['attempt_count'] == 0 for row in report['rows'])
        assert control('resume')['dispatched'] is False
        assert request('batches/report?batch_id='+batch_id)['report']['paused'] is False
        cursor = None
        found = False
        while True:
            page = request('batches?limit=1'+('&after='+cursor if cursor else ''))
            found |= any(item['batch_id'] == batch_id for item in page['batches'])
            cursor = page['next_cursor']
            if cursor is None:
                break
        assert found
        for path, body in [('batches/report?batch_id=..%2Foutside', None),
                           ('batches/control', {'batch_id': batch_id, 'action': 'delete'})]:
            try:
                request(path, body)
            except HTTPError as exc:
                assert exc.code == 400
                assert json.load(exc)['ok'] is False
            else:
                raise AssertionError('Invalid batch request accepted')
        after = request('session/status')['session']
        assert (after['run_id'], after['state']) == (before['run_id'], before['state'])
    finally:
        # Leave this deliberately non-executable fixture paused, not runnable.
        assert control('pause')['paused'] is True
    result = {'passed': True, 'batch_id': batch_id, 'dispatched': False,
              'stale_scheduler_cancel_rejected': True,
              'session_unchanged': True, 'fixture_paused': True}
    output = ROOT/'runs/validation/batch-http.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
