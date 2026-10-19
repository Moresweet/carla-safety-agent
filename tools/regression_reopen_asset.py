"""Read-only HTTP acceptance for reopening one existing Blender export."""
import hashlib
import json
import uuid
from urllib.error import HTTPError
from urllib.request import urlopen
from cleanup_superseded_model_captures import ROOT, idle


def main():
    job = '0f92d5997ced'
    folder = ROOT / '.runtime/blender-assets' / job
    def inventory():
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob('*') if p.is_file()}
    idle()
    before = inventory()
    rows = []
    for query, expected in [('job_id='+job, 200), ('job_id='+job+'&job_id=', 400),
                            ('job_id='+job+'&extra=', 400), ('job_id=..%2Foutside', 400),
                            ('job_id=missingfixture', 400)]:
        try:
            with urlopen('http://127.0.0.1:8765/blender/exported?'+query, timeout=20) as response:
                status, body = response.status, json.load(response)
        except HTTPError as error:
            status, body = error.code, json.load(error)
        assert status == expected, (status, body)
        assert body['ok'] is (status == 200)
        if status == 200:
            assert body['job_id'] == job and body['reopened'] is True
            assert set(body['outputs']) == {'blend', 'glb', 'fbx'}
        rows.append({'query': query, 'status': status})
    assert inventory() == before
    idle()
    receipt = ROOT / 'runs/validation' / ('reopen-asset-' + uuid.uuid4().hex + '.json')
    result = {'passed': True, 'job_id': job, 'cases': rows,
              'source_unchanged': True, 'files': before, 'native_tools_started': False}
    receipt.write_text(json.dumps(result, indent=2))
    print(json.dumps({'receipt': str(receipt), **result}))


if __name__ == '__main__':
    main()
