import json
import pytest
from carla_safety_agent.session import SessionJournal
from carla_safety_agent.experiment_queue import ExperimentQueue


def test_lost_response_binding_and_ambiguity(tmp_path):
    dimensions = {**{a: [{'id': 'base', 'configuration': {}}]
                    for a in ('scenes', 'models', 'weather', 'textures')}, 'seeds': [0]}
    q = ExperimentQueue(tmp_path/'queue'); q.create(dimensions); claim = q.claim()
    job, attempt = claim['job_id'], claim['attempt']['attempt_id']
    journal = SessionJournal(tmp_path/'data')
    assert q.recover_binding(job, attempt, journal)['bound'] is False
    assert q.read()['jobs'][0]['state'] == 'reserved'
    def record(run):
        folder = tmp_path/'data/experiments'/run; folder.mkdir(parents=True)
        (folder/'execution.json').write_text(json.dumps({'run_id': run, 'state': 'running',
            'configuration': {'request': {'batch_attempt_id': attempt, 'batch_job_id': job}}}))
    record('run1')
    assert q.recover_binding(job, attempt, journal) == {'bound': True, 'execution_id': 'run1'}
    assert q.read()['jobs'][0]['attempts'][0]['execution_id'] == 'run1'
    record('run2')
    with pytest.raises(ValueError, match='Multiple'): journal.find_batch_attempt(attempt, job)
    with pytest.raises(ValueError, match='another job'): journal.find_batch_attempt(attempt, 'wrong')
