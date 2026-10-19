"""Register two documented acceptance baselines; never delete or unprotect data."""
import argparse
import json
from pathlib import Path

from carla_safety_agent.capture_retention import CaptureRetention

ROOT = Path(__file__).resolve().parents[1]
REVIEWED = {
    'capture-20260908T131711-80c015a7': (
        'docs/DEVELOPMENT_PLAN.md',
        '人工驾驶、看门狗制动及事件回放验收基线；依据 docs/DEVELOPMENT_PLAN.md，120 样本。'),
    'capture-20260910T180331-b461bbb2': (
        'docs/PREDICTION_SPATIAL_CONTRACT.md',
        'UniAD-Tiny 实际类名识别失败的预测契约反例；依据 docs/PREDICTION_SPATIAL_CONTRACT.md，保留原失败数据，不回写为通过。'),
}


def protect(root=ROOT, *, execute=False):
    root = Path(root)
    store = CaptureRetention(root/'data', root/'.runtime/generated-scenarios')
    state = store.snapshot()
    # Check every evidence document before the first mutation.
    for run, (document, _) in REVIEWED.items():
        if run not in (root/document).read_text():
            raise ValueError('Documented baseline reference missing: '+run)
        path = store.capture_root/run
        if path.is_symlink() or not path.is_dir():
            raise ValueError('Baseline directory missing or linked: '+run)
        from carla_safety_agent.scene_store import read_json
        if read_json(path/'manifest.json').get('run_id') != run:
            raise ValueError('Baseline identity mismatch: '+run)
    changes=[]
    for run, (_, reason) in REVIEWED.items():
        if run in state['records']:
            changes.append({'run_id':run, 'action':'preserved_existing_marker'})
            continue
        if execute:
            state=store.set_keep(run, True, reason, expected_revision=state['revision'])
        changes.append({'run_id':run, 'action':'protected' if execute else 'would_protect', 'reason':reason})
    return {'executed':execute, 'revision':state['revision'], 'changes':changes, 'deleted':[]}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    print(json.dumps(protect(execute=args.execute),ensure_ascii=False,indent=2))
