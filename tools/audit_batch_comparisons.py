"""Recompute comparisons from existing ledgers, without starting any execution."""
import hashlib
import itertools
import json
import uuid
from pathlib import Path
from carla_safety_agent.scene_store import read_json
from carla_safety_agent.experiment_report import summarize_queue, compare_variants


def main():
    root=Path(__file__).resolve().parents[1]
    results={'rule-run':root/'runs/rule','run':root/'runs/uniad'}
    evidence=[]
    for path in sorted((root/'data/experiment-queues').glob('*/queue.json')):
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        row={'batch_id':path.parent.name,'ledger_sha256':digest,'comparisons':[]}
        try:
            report=summarize_queue(read_json(path,max_bytes=32*1024**2),results)
            row['states']=report['state_counts']
            for axis in ('scenes','models','weather','textures'):
                variants=sorted({entry['variants'][axis] for entry in report['rows']})
                for baseline,candidate in itertools.combinations(variants,2):
                    comparison=compare_variants(report,axis,baseline,candidate)
                    assert comparison['comparable_count']+comparison['excluded_count']==len(comparison['pairs'])
                    assert sum(comparison['exclusion_counts'].values())==comparison['excluded_count']
                    row['comparisons'].append(comparison)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Ledger changed during audit')
            row['checked']=True
        except Exception as error:row.update(checked=False,error=str(error))
        evidence.append(row)
    output=root/'runs/validation'/('batch-comparison-audit-'+uuid.uuid4().hex+'.json')
    payload={'scope':'Read-only historical ledger and referenced result audit; no new model runs or driving-quality claim',
             'batches':evidence,'checked':sum(row['checked'] for row in evidence)}
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print(json.dumps({'receipt':str(output),'checked':payload['checked'],'total':len(evidence),
        'comparisons':sum(len(row['comparisons']) for row in evidence),
        'comparable_pairs':sum(c['comparable_count'] for row in evidence for c in row['comparisons']),
        'excluded_pairs':sum(c['excluded_count'] for row in evidence for c in row['comparisons'])}))
    if not evidence or payload['checked']!=len(evidence):raise SystemExit(1)


if __name__=='__main__':main()
