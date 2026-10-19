"""Record final read-only service, native-world and local validation evidence."""
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import uuid

import carla
from carla_safety_agent.world_health import observe_idle

ROOT = Path(__file__).resolve().parents[1]
NODE = '/home/moresweet/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'

def main():
    output = ROOT / 'runs/validation' / ('final-health-' + uuid.uuid4().hex)
    output.mkdir()
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'state': 'running'}
    for route in ('session/status', 'system/preflight'):
        with urllib.request.urlopen('http://127.0.0.1:8765/' + route, timeout=30) as response:
            report[route] = json.load(response)
    with urllib.request.urlopen('http://127.0.0.1:3000/', timeout=30) as response:
        report['frontend_status'] = response.status
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(15)
    report['world'] = observe_idle(client, client.get_world().get_map().name)
    report['disk_free_bytes'] = shutil.disk_usage(ROOT).free
    report['process_list'] = subprocess.check_output(['pgrep', '-af', 'UE4Editor|livery_bridge.py|vinext dev'], text=True)
    report['checks'] = []
    commands = [['python3', '-m', 'pytest', '-q', '--tb=short'],
        [NODE, 'tools/livery-designer/node_modules/typescript/bin/tsc', '--noEmit', '-p', 'tools/livery-designer/tsconfig.json'],
        *[[NODE, 'tools/' + name] for name in ('test_preview_uv.mjs', 'test_texture_target.mjs', 'test_object_origin.mjs', 'test_transform_draft.mjs')],
        ['git', 'diff', '--check']]
    for index, command in enumerate(commands):
        result = subprocess.run(command, text=True, capture_output=True, cwd=ROOT)
        log = output / f'check-{index}.log'
        log.write_text(result.stdout + result.stderr)
        report['checks'].append({'command': command, 'returncode': result.returncode, 'log': str(log)})
    report['diagnostics'] = {}
    for name, terms in [('carla.log', ['Caught signal', 'Segmentation fault', 'Invalid texture in SRT']),
                        ('bridge.log', ['World changed while this operation waited', 'BrokenPipeError'])]:
        source = ROOT / '.runtime' / name
        lines = source.read_text(errors='replace').splitlines()
        scope = 'Bridge log has no request timestamps; historical and current entries may coexist'
        if name == 'carla.log':
            start = next(i for i, line in enumerate(lines) if '[2026.09.14-' in line)
            lines = lines[start:]
            scope = 'CARLA log from first 2026-09-14 timestamp; earlier September crash records excluded'
        matches = [line for line in lines if any(term in line for term in terms)]
        excerpt = output / (name + '.excerpt.txt')
        excerpt.write_text('\n'.join(matches[-30:]))
        report['diagnostics'][name] = {'counts': {term: sum(term in line for line in matches) for term in terms},
            'excerpt': str(excerpt), 'scope': scope + '; counts are matching lines, not incident counts'}
    report['state'] = 'passed' if (report['system/preflight']['ready'] and report['frontend_status'] == 200
        and report['session/status']['session']['state'] in ('completed', 'stopped', 'idle')
        and not report['world']['synchronous'] and report['world']['sensors'] == 0
        and all(check['returncode'] == 0 for check in report['checks'])) else 'failed'
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'output': str(output), 'state': report['state'], 'world': report['world']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
