import importlib.util
from pathlib import Path
import pytest


@pytest.fixture
def receipt(tmp_path):
    path = Path(__file__).resolve().parents[1] / 'tools/inventory_original_model_dependencies.py'
    spec = importlib.util.spec_from_file_location('receipt_tool', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ('a', 'b', 'shared'):
        (tmp_path / name).write_text(name)
    data = {'schema': 'original-model-dependency-receipt/1',
        'models': {model: {'files': {name: module.fingerprint(tmp_path / name)}}
                   for model, name in [('thinktwice', 'a'), ('driveadapter', 'b')]},
        'shared_adaptations': {'shared': module.fingerprint(tmp_path / 'shared')}}
    return module, data


def test_intact_modified_and_missing_files(tmp_path, receipt):
    module, data = receipt
    assert module.verify_receipt(tmp_path, data)['ok']
    (tmp_path / 'a').write_text('changed')
    (tmp_path / 'b').unlink()
    result = module.verify_receipt(tmp_path, data)
    assert not result['ok'] and len(result['failures']) == 2
    assert not result['restoration_verified']


@pytest.mark.parametrize('path', ['../outside', '/etc/passwd', 'a/../b', 'a\\b'])
def test_untrusted_paths_rejected(tmp_path, receipt, path):
    module, data = receipt
    data['shared_adaptations'] = {path: data['shared_adaptations']['shared']}
    with pytest.raises(ValueError): module.verify_receipt(tmp_path, data)
