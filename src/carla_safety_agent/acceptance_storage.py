"""Admission budget for the fixed 80-frame original-model acceptance run.

Not a disk quota: the per-sample recorder reserve remains necessary because
other processes can consume space after admission. Never removes recordings.
"""
import shutil


def require_original_capture_space(root, *, capture_count=1, disk_usage=shutil.disk_usage):
    # Observed full captures use about 3 GiB; budget 4 GiB for this fixed rig
    # and retain 2 GiB for the host and evidence files. Not for arbitrary rigs.
    if type(capture_count) is not int or not 1 <= capture_count <= 10:
        raise ValueError('capture_count must be an integer from 1 to 10')
    estimated = capture_count * 4 * 1024**3
    retained = 2 * 1024**3
    free = disk_usage(root).free
    if free < estimated + retained:
        raise RuntimeError(
            f'{capture_count} x 80-frame capture requires {estimated + retained} free bytes '
            f'({capture_count * 4} GiB capture budget + 2 GiB retained); available {free}. '
            'No capture started and no historical data deleted.')
    return {'free_bytes': free, 'capture_budget_bytes': estimated,
            'capture_count': capture_count, 'required_free_bytes': estimated + retained,
            'retained_bytes': retained, 'scope': 'Fixed 80-frame original-model rig; not a quota'}
