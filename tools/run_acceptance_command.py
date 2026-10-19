"""Run one explicit acceptance command, retaining logs, scene images and new evidence."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('An explicit command is required')
    root = Path(__file__).resolve().parents[1]
    validation = root / 'runs/validation'
    before = set(validation.rglob('*'))
    output = validation / ('acceptance-20260914-' + uuid.uuid4().hex)
    output.mkdir()
    report = {'name': args.name, 'command': command,
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'state': 'running', 'screenshots': [], 'evidence': []}
    def save():
        (output / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    def scene(label):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/scene/preview', timeout=20) as response:
                content = response.read()
            if not content.startswith(b'\xff\xd8'):
                raise ValueError('Scene preview is not JPEG')
            path = output / (label + '.jpg')
            path.write_bytes(content)
            report['screenshots'].append(str(path))
        except Exception as exc:
            report.setdefault('screenshot_errors', []).append({'step': label, 'error': str(exc)})
    save()
    scene('before')
    started = time.monotonic()
    print(json.dumps({'name': args.name, 'state': 'running', 'report': str(output)}, ensure_ascii=False), flush=True)
    # Do not timeout-kill a command that may currently own simulator resources.
    with (output / 'command.log').open('w') as log:
        result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
    report.update(returncode=result.returncode, seconds=time.monotonic() - started,
                  state='passed' if result.returncode == 0 else 'failed')
    scene('after')
    report['evidence'] = sorted(str(p) for p in set(validation.rglob('*')) - before
                                if p.is_file() and output not in p.parents and p.suffix in ('.json', '.jpg', '.png'))
    save()
    print(json.dumps({'name': args.name, 'state': report['state'], 'report': str(output / 'acceptance.json')}, ensure_ascii=False), flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
