import importlib.util
from collections import OrderedDict
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


class Tensor:
    def __init__(self, value):
        self.value = value
        self.shape = value.shape
    def permute(self, *axes):
        return Tensor(self.value.transpose(axes))
    def contiguous(self):
        return Tensor(self.value.copy())


@pytest.fixture
def convert(monkeypatch):
    class Sparse:
        ndim = 3
        kernel_size = [2, 3, 4]
        in_channels = 5
        out_channels = 6
        weight = SimpleNamespace(shape=(6, 2, 3, 4, 5))
    monkeypatch.setitem(sys.modules, 'spconv.constants', SimpleNamespace(SAVED_WEIGHT_LAYOUT=''))
    monkeypatch.setitem(sys.modules, 'spconv.pytorch.conv', SimpleNamespace(SparseConvolution=Sparse))
    path = Path(__file__).resolve().parents[1] / 'tools/legacy_sparse_weights.py'
    spec = importlib.util.spec_from_file_location('legacy_sparse_weights', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.convert_rsck_state, Sparse


def test_explicit_axes_only_real_sparse_modules_and_original_unchanged(convert):
    function, Sparse = convert
    state = OrderedDict({'s.weight': Tensor(np.arange(720).reshape(2,3,4,5,6)),
                         'other.weight': Tensor(np.ones((2,3,4,5,6)))})
    state._metadata = {'s': {'version': 1}, 'other': {'version': 7}}
    model = SimpleNamespace(named_modules=lambda: [('s', Sparse()), ('other', object())])
    result, records = function(model, state)
    assert result['s.weight'].value[5,1,2,3,4] == state['s.weight'].value[1,2,3,4,5]
    np.testing.assert_array_equal(result['s.weight'].value.transpose(1,2,3,4,0), state['s.weight'].value)
    assert state._metadata['s']['version'] == 1
    assert result._metadata['s']['version'] == 2
    assert result._metadata['other']['version'] == 7
    assert result['other.weight'] is state['other.weight']
    assert len(records) == 1


def test_wrong_layout_and_empty_model_rejected(convert):
    function, Sparse = convert
    model = SimpleNamespace(named_modules=lambda: [('', Sparse())])
    with pytest.raises(ValueError, match='RSCK'):
        function(model, {'weight': Tensor(np.zeros((6,2,3,4,5)))})
    with pytest.raises(ValueError, match='No real'):
        function(SimpleNamespace(named_modules=lambda: []), {})


def test_implicit_second_conversion_rejected(convert, monkeypatch):
    function, _ = convert
    monkeypatch.setitem(sys.modules, 'spconv.constants', SimpleNamespace(SAVED_WEIGHT_LAYOUT='RSCK'))
    with pytest.raises(ValueError, match='twice'):
        function(None, {})
