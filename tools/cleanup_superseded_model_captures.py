"""Explicit one-off deletion of two reviewed, superseded model captures.

Requires --execute. Raw samples are not backed up and cannot be restored.
"""
import argparse
import json
from pathlib import Path
import shutil
import uuid
from regression_scene_versions import ROOT, request
from carla_safety_agent.capture_retention import CaptureRetention
from carla_safety_agent.capture_references import capture_references, queue_references
from carla_safety_agent.split_registry import require_no_registered_split_references, registry_mutation_lock
from carla_safety_agent.capture_recovery import inventory, require_inactive_execution
from carla_safety_agent.restart_guard import verify_dataset_jobs_idle, verify_idle, verify_handoff_idle

PAIRS={
 'capture-20260914T162209-4ac2b23f':'capture-20260915T183736-10c0f89d',
 'capture-20260914T164050-27b18bb2':'capture-20260915T180324-f1610aad',
}
REVIEWED_SHORT_PAIRS={
 'capture-20260908T190538-4623c606':'capture-20260914T121755-0614ba09',
 'capture-20260908T192516-57adf886':'capture-20260914T122657-cbac5022',
}
VAD_MAP_PAIRS={
 'capture-20260910T143709-0df045ed':'capture-20260910T211256-dbb150cc',
 'capture-20260910T143955-279b2b89':'capture-20260910T211542-2fdf5337',
}
DRIVE_NAV_PAIRS={'capture-20260915T180324-f1610aad':'capture-20260915T213258-365bc848'}


def idle():
    verify_idle(request('session/status')['session'],request('batches/scheduler')['scheduler'])
    verify_dataset_jobs_idle(request('datasets/jobs'))
    verify_handoff_idle(request('scenes/handoff'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true',required=True)
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument('--reviewed-short-baselines',action='store_true',
                        help='Only the two explicitly reviewed 20260908 VAD/UniAD-base captures')
    selection.add_argument('--vad-map-baselines',action='store_true',help='Only the superseded first VAD map roundtrip')
    selection.add_argument('--drive-navigation-baseline',action='store_true',help='Only the earliest DriveAdapter80 baseline replaced by the navigation-observation80 baseline')
    args=parser.parse_args()
    pairs=REVIEWED_SHORT_PAIRS if args.reviewed_short_baselines else PAIRS
    if args.vad_map_baselines:pairs=VAD_MAP_PAIRS
    if args.drive_navigation_baseline:pairs=DRIVE_NAV_PAIRS
    expected_frames=20 if args.reviewed_short_baselines or args.vad_map_baselines else 80
    root=ROOT/'.runtime/generated-scenarios'
    if root.is_symlink():raise ValueError('Linked capture root refused')
    idle()
    markers=CaptureRetention(ROOT/'data',root).snapshot()
    require_no_registered_split_references(ROOT/'data/dataset-splits', pairs)
    derived=capture_references(root);queues=queue_references(ROOT/'data/experiment-queues')
    if not derived['complete'] or not queues['complete']:raise ValueError('Reference checks incomplete')
    out=ROOT/'runs/validation'/('superseded-cleanup-'+uuid.uuid4().hex);out.mkdir()
    rows=[]
    for old,new in pairs.items():
        source=root/old;replacement=root/new
        if source.is_symlink() or replacement.is_symlink():raise ValueError('Linked capture refused')
        manifest=json.loads((source/'manifest.json').read_text())
        newer=json.loads((replacement/'manifest.json').read_text())
        if manifest['run_id']!=old or newer['run_id']!=new:raise ValueError('Identity mismatch')
        if any(m['status']!='saved' or m['frame_count']!=expected_frames for m in (manifest,newer)):raise ValueError('Expected finalized reviewed baselines')
        if manifest['model']!=newer['model']:raise ValueError('Replacement model differs')
        if old in markers['records'] or new not in markers['records']:raise ValueError('Retention state changed')
        if derived['references'].get(old) or queues['references'].get(manifest['execution_id']):raise ValueError('Source now referenced')
        for m in (manifest,newer):require_inactive_execution(ROOT/'data',m['execution_id'])
        evidence,_=inventory(source)
        saved=out/'metadata'/old;saved.mkdir(parents=True)
        for name in ('manifest.json','index.json','calibration.json','scenario.json','collisions.json'):
            path=source/name
            if path.is_file():shutil.copy2(path,saved/name)
        scenario=manifest.get('scenario')
        if isinstance(scenario,dict):
            name=scenario.get('path')
            if not isinstance(name,str) or Path(name).name!=name:raise ValueError('Unsafe scenario metadata path')
            shutil.copy2(source/name,saved/name)
        rows.append({'source':old,'replacement':new,'files':evidence})
    with (out/'plan.json').open('x') as stream:json.dump({'rows':rows,'raw_recoverable':False},stream,indent=2)
    before=shutil.disk_usage(root).free
    for row in rows:
        idle()
        if CaptureRetention(ROOT/'data',root).snapshot()!=markers:raise ValueError('Retention changed')
        refs=capture_references(root);q=queue_references(ROOT/'data/experiment-queues')
        manifest=json.loads((root/row['source']/'manifest.json').read_text())
        if not refs['complete'] or not q['complete'] or refs['references'].get(row['source']) or q['references'].get(manifest['execution_id']):raise ValueError('References changed')
        require_inactive_execution(ROOT/'data',manifest['execution_id'])
        source=root/row['source']
        if inventory(source)[0]!=row['files']:raise ValueError('Source changed since review')
        with registry_mutation_lock(ROOT/'data/dataset-splits'):
            require_no_registered_split_references(ROOT/'data/dataset-splits', [row['source']])
            shutil.rmtree(source)
        with (out/'deleted.jsonl').open('a') as stream:stream.write(json.dumps({'source':row['source'],'replacement':row['replacement'],'raw_recoverable':False})+'\n')
    idle()
    result={'deleted':list(pairs),'replacements_preserved':all((root/new).is_dir() for new in pairs.values()),
        'free_before':before,'free_after':shutil.disk_usage(root).free,'raw_recoverable':False}
    with (out/'result.json').open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({'receipt':str(out),**result}))


if __name__=='__main__':main()
