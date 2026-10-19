import json
import pytest
from carla_safety_agent.capture_references import capture_references, split_references, queue_references
from carla_safety_agent.dataset_split import split_runs


def test_queue_indexes_all_attempts_including_retries(tmp_path):
    folder = tmp_path/'queue-a'
    folder.mkdir()
    doc = {'schema_version':'carla-experiment-queue/1', 'jobs':[{'job_id':'job-a',
        'attempts':[{'attempt_id':'try-1','execution_id':'execution-old','state':'failed'},
                    {'attempt_id':'try-2','execution_id':'execution-new'},
                    {'attempt_id':'try-3','execution_id':None}]}]}
    path = folder/'queue.json'
    path.write_text(json.dumps(doc))
    before = path.read_bytes()
    result = queue_references(tmp_path)
    assert result['complete']
    assert set(result['references']) == {'execution-old','execution-new'}
    assert result['references']['execution-old'][0]['attempt_id'] == 'try-1'
    assert path.read_bytes() == before


@pytest.mark.parametrize('case', ['missing', 'linked', 'malformed', 'limit'])
def test_queue_incomplete_is_not_no_references(tmp_path, case):
    folder = tmp_path/'a'
    folder.mkdir()
    if case == 'linked':
        (folder/'queue.json').symlink_to(tmp_path/'elsewhere')
    elif case == 'malformed':
        (folder/'queue.json').write_text('{}')
    elif case == 'limit':
        (folder/'queue.json').write_text(json.dumps({'schema_version':'carla-experiment-queue/1','jobs':[]}))
        (tmp_path/'b').mkdir()
    result = queue_references(tmp_path,max_queues=1)
    assert not result['complete'] and result['warnings']


def test_split_reference_reads_generated_contract_without_modifying(tmp_path):
    path = tmp_path/'split.json'
    path.write_text(json.dumps(split_runs([{'run_id':'capture-a','scene_group':'scene-a'}])))
    before = path.read_bytes()
    result = split_references([path])
    assert result['complete'] and result['scanned_files'] == 1
    assert result['references']['capture-a'][0]['kind'] == 'split'
    assert path.read_bytes() == before


@pytest.mark.parametrize('case', ['missing', 'linked', 'invalid', 'mismatch', 'duplicate'])
def test_split_errors_never_report_complete(tmp_path, case):
    path = tmp_path/'split.json'
    doc = split_runs([{'run_id':'capture-a','scene_group':'scene-a'}])
    if case == 'invalid': doc['assignments']['test'] = '../escape'
    if case == 'duplicate': doc['assignments']['test'] += ['capture-a','capture-a']
    if case == 'mismatch': doc['datasets'] = {'capture-extra':{}}
    if case != 'missing': path.write_text(json.dumps(doc))
    if case == 'linked':
        link = tmp_path/'link.json'
        link.symlink_to(path)
        path = link
    result = split_references([path])
    assert not result['complete'] and result['warnings']
    if case == 'mismatch': assert 'capture-extra' in result['references']


def manifest(root, name, **extra):
    folder = root/name
    folder.mkdir()
    (folder/'manifest.json').write_text(json.dumps({'run_id':name, **extra}))


def test_recovery_and_excerpt_protect_sources_and_report_missing(tmp_path):
    manifest(tmp_path,'capture-source')
    manifest(tmp_path,'recovered-copy',recovery={'source_run_id':'capture-source'})
    manifest(tmp_path,'excerpt-copy',excerpt={'source_run_id':'capture-source'})
    manifest(tmp_path,'excerpt-orphan',excerpt={'source_run_id':'missing-source'})
    result = capture_references(tmp_path)
    assert result['complete']
    assert len(result['references']['capture-source']) == 2
    assert result['missing_sources'] == ['missing-source']


@pytest.mark.parametrize('reference', [None, {}, {'source_run_id':'../escape'}, {'source_run_id':'self'}])
def test_invalid_derived_reference_does_not_mean_unreferenced(tmp_path, reference):
    manifest(tmp_path,'self',recovery=reference)
    result = capture_references(tmp_path)
    assert not result['complete'] and result['warnings']


def test_scan_limit_and_link_are_explicitly_incomplete(tmp_path):
    manifest(tmp_path,'a')
    manifest(tmp_path,'b')
    assert not capture_references(tmp_path,max_manifests=1)['complete']
    (tmp_path/'linked').symlink_to(tmp_path/'a',target_is_directory=True)
    assert not capture_references(tmp_path)['complete']
