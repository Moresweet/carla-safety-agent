import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('baseline_protection',Path(__file__).resolve().parents[1]/'tools/protect_reviewed_capture_baselines.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def fixture(root):
    for run,(document,_) in module.REVIEWED.items():
        path=root/document;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(run)
        folder=root/'.runtime/generated-scenarios'/run;folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps({'run_id':run}))

def test_dry_run_then_idempotent_keep(tmp_path):
    fixture(tmp_path)
    assert not module.protect(tmp_path)['executed']
    assert not (tmp_path/'data').exists()
    result=module.protect(tmp_path,execute=True)
    assert result['revision']==2 and not result['deleted']
    before=(tmp_path/'data/capture-retention.json').read_bytes()
    assert all(r['action']=='preserved_existing_marker' for r in module.protect(tmp_path,execute=True)['changes'])
    assert (tmp_path/'data/capture-retention.json').read_bytes()==before

def test_missing_second_evidence_prevents_all_mutation(tmp_path):
    fixture(tmp_path)
    (tmp_path/list(module.REVIEWED.values())[1][0]).write_text('unrelated')
    with pytest.raises(ValueError):module.protect(tmp_path,execute=True)
    assert not (tmp_path/'data').exists()
