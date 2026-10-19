from types import SimpleNamespace
import pytest
from carla_safety_agent.acceptance_storage import require_original_capture_space


@pytest.mark.parametrize('free', [0, 5 * 1024**3, 6 * 1024**3 - 1])
def test_insufficient_fixed_rig_budget_refuses_without_mutating(tmp_path, free):
    original = tmp_path / 'history'
    original.write_text('keep')
    with pytest.raises(RuntimeError, match='No capture started'):
        require_original_capture_space(tmp_path, disk_usage=lambda _: SimpleNamespace(free=free))
    assert original.read_text() == 'keep'
    assert list(tmp_path.iterdir()) == [original]


def test_exact_budget_records_estimate_and_retained_space(tmp_path):
    result = require_original_capture_space(tmp_path,
        disk_usage=lambda _: SimpleNamespace(free=6 * 1024**3))
    assert result['free_bytes'] == result['capture_budget_bytes'] + result['retained_bytes']


@pytest.mark.parametrize('count', [1, 2, 10])
def test_multi_capture_budget_is_aggregate_not_single_run(tmp_path, count):
    needed = (count * 4 + 2) * 1024**3
    with pytest.raises(RuntimeError):
        require_original_capture_space(tmp_path, capture_count=count,
            disk_usage=lambda _:SimpleNamespace(free=needed-1))
    receipt = require_original_capture_space(tmp_path, capture_count=count,
        disk_usage=lambda _:SimpleNamespace(free=needed))
    assert receipt['capture_count'] == count
    assert receipt['required_free_bytes'] == needed
    assert receipt['capture_budget_bytes'] == count * 4 * 1024**3


@pytest.mark.parametrize('count', [0, -1, 11, True, 1.5, '2', None])
def test_invalid_capture_count_rejected_before_disk_access(tmp_path, count):
    def forbidden(_): pytest.fail('Invalid count inspected disk')
    with pytest.raises(ValueError):
        require_original_capture_space(tmp_path, capture_count=count, disk_usage=forbidden)
