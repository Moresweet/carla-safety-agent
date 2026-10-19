"""Validate original OpenDriveLab warmup and spatial predictions in saved frames."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.prediction_trajectory import replay_prediction


def main():
    if not __debug__:
        raise RuntimeError('Prediction validation requires assertions; do not use Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--model', choices=('thinktwice', 'driveadapter'), default='thinktwice')
    parser.add_argument('--require-navigation',action='store_true',help='Require saved DriveAdapter navigation diagnostics on every predicted frame')
    parser.add_argument('--require-map-projection',action='store_true',help='Require archived-map projection and v2 runtime navigation parameters on every predicted frame')
    parser.add_argument('--output',type=Path,help='Write a new validation receipt; never overwrite')
    args = parser.parse_args()
    if args.require_map_projection:args.require_navigation=True
    if args.require_navigation and args.model!='driveadapter':
        parser.error('Navigation observation is currently DriveAdapter-only')
    frames = sorted((args.dataset/'samples').glob('*/frame.json'))
    if len(frames) <= 31:
        raise ValueError('Run must include real inference after history warmup')
    warmup = predicted = 0
    navigation=[]
    projected=[]
    manifest=json.loads((args.dataset/'manifest.json').read_text()) if args.require_map_projection else None
    previous_frame = None
    for path in frames:
        data = json.loads(path.read_text())
        if data['model'] != args.model + '-experimental':
            raise ValueError('Capture does not match the requested original model')
        step = data['model_step']
        assert step == warmup+predicted, 'Expected consecutive original model steps'
        if previous_frame is not None:
            assert data['frame'] == previous_frame+1, 'Missing simulator frame'
        previous_frame = data['frame']
        prediction = data['prediction']
        if step < 31:
            assert prediction['state'] == 'warmup'
            assert data['planning_anchor'] is None
            assert data['planning_observed_calls'] == 0
            warmup += 1
        else:
            assert prediction['state'] == 'available', prediction
            assert data['planning_anchor']['frame'] == data['frame']
            assert data['planning_anchor']['model_step'] == step
            assert data['planning_observed_calls'] == step-30
            overlay = replay_prediction(data, data['ego']['matrix'])
            assert overlay['state'] == 'available', overlay
            assert len(overlay['points']) == 4
            assert overlay['prediction_age_s'] == 0
            assert not overlay['timing_verified'] and not overlay['error_metrics_computed']
            if args.require_navigation:
                diagnostic=overlay.get('navigation_diagnostic')
                assert isinstance(diagnostic,dict) and diagnostic.get('state')=='available',diagnostic
                assert diagnostic['source_frame']==data['frame']
                assert diagnostic['reference_equivalence_verified'] is False
                navigation.append(diagnostic)
            if args.require_map_projection:
                import numpy as np
                from carla_safety_agent.offline_projection import archived_prediction
                assert data['planning_anchor']['navigation_reference']['schema_version']=='driveadapter-navigation-observation/2', 'Runtime navigation parameters were not recorded'
                converted=archived_prediction(args.dataset,manifest,data,np.asarray(data['ego']['matrix']))
                assert converted['state']=='available',converted
                assert converted['navigation_parameter_source']=='saved_runtime_parameters'
                assert converted['source_frame']==data['frame'] and len(converted['points'])==4
                projected.append(converted)
            predicted += 1
    assert warmup == 31 and predicted == len(frames)-31
    report={'ok': True, 'dataset':str(args.dataset.resolve()), 'model': args.model, 'warmup_frames': warmup, 'prediction_frames': predicted,
                      'navigation':({'frames':len(navigation),
                          'position_delta_min_m':min(x['position_delta_m'] for x in navigation),
                          'position_delta_max_m':max(x['position_delta_m'] for x in navigation),
                          'heading_delta_max_abs_rad':max(abs(x['heading_delta_rad']) for x in navigation),
                          'reference_equivalence_verified':False} if navigation else None),
                      'map_projection':({'frames':len(projected),
                          'map_sha256':manifest['map_projection']['sha256'],
                          'navigation_delta_max_m':max(x['navigation_position_delta_m'] for x in projected),
                          'runtime_parameters_verified':True} if projected else None),
                      'scope': 'Observed original PID spatial output, not future trajectory accuracy'}
    if args.output:
        with args.output.open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
