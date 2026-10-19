"""Replay real lifecycle metadata without recording or modifying source reports."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from carla_safety_agent.prediction_trajectory import replay_prediction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be new')
    rows = []
    for path in args.reports:
        before = path.read_bytes()
        for entry in json.loads(before):
            assert entry['passed'] is True
            metadata = entry['planning_capture']
            pose = np.asarray(metadata['ego']['matrix'])
            origin = np.asarray(metadata['planning_anchor']['ego_matrix'])
            result = replay_prediction(metadata, pose)
            assert result['state'] == 'available', result
            assert result['timing_verified'] is False
            assert result['error_metrics_computed'] is False
            assert result['source_frame'] == metadata['planning_anchor']['frame']
            assert result['reused'] == (result['source_frame'] != metadata['frame'])
            assert len(result['points']) == len(metadata['prediction']['right_forward_m'])
            # Independently reconstruct expected world positions from the source
            # reference, then compare with the replay's current-body positions.
            residuals = []
            for raw, point in zip(metadata['prediction']['right_forward_m'], result['points']):
                right, forward = raw
                if result['contract']['reference'] == 'virtual_lidar':
                    expected = origin @ [forward - .39, right, 1.84, 1]
                else:
                    heading = origin[:2, 0] / np.linalg.norm(origin[:2, 0])
                    expected = origin[:, 3].copy()
                    expected[:2] += heading * forward + np.array([-heading[1], heading[0]]) * right
                actual = pose @ [*point['xyz_m'], 1]
                residuals.append(float(np.linalg.norm(actual - expected)))
                assert point['dt_s'] is None
            assert max(residuals) < 1e-6
            rows.append({'model': entry['model'], 'execution_id': entry['execution_id'],
                         'source_report': str(path), 'source_sha256': hashlib.sha256(before).hexdigest(),
                         'capture_frame': metadata['frame'], 'replay': result,
                         'max_world_residual_m': max(residuals)})
        assert path.read_bytes() == before, 'Source report changed'
    with args.output.open('x') as stream:
        json.dump({'passed': True, 'scope': 'Real saved lifecycle metadata through replay geometry; not a full recording/browser replay or timing validation',
                   'rows': rows}, stream, indent=2)
    print(json.dumps({'passed': True, 'models': [r['model'] for r in rows],
                      'reused': [r['model'] for r in rows if r['replay']['reused']],
                      'output': str(args.output)}))


if __name__ == '__main__':
    main()
