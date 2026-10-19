"""Install exact reviewed RPC candidate, preserving every replaced file."""
import hashlib
import json
from pathlib import Path
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    candidate = Path('/tmp/safeagent-rpclib-close-libcxx-build/librpc.a')
    header = Path('/tmp/safeagent-rpclib-close-review/include/rpc/detail/async_writer.h')
    roots = [Path('/home/moresweet/carla/Build/rpclib-carla-callbacks-c10-libcxx-install'),
             Path('/home/moresweet/carla/Unreal/CarlaUE4/Plugins/Carla/CarlaDependencies')]
    assert digest(candidate) == '88d769830efca5843bd636a16dfd4144a7038b945a15ac7a2dfa8ba551e0a4fb'
    replacements = []
    for root in roots:
        target = root / 'lib/librpc.a'
        assert not target.is_symlink()
        assert digest(target) == 'ae8069508fa33b7a7cc5d09694a3bffe0496d50a7a16b14143471da9d223f468'
        replacements.extend([(candidate, target), (header, root / 'include/rpc/detail/async_writer.h')])
    originals = [target for _, target in replacements if target.name == 'async_writer.h']
    assert originals[0].read_bytes() == originals[1].read_bytes()
    assert b'socket_.close();' in originals[0].read_bytes()
    out = ROOT / 'runs/validation' / ('rpc-install-' + uuid.uuid4().hex)
    out.mkdir()
    rows = []
    for index, (source, target) in enumerate(replacements):
        if target.is_symlink() or source.is_symlink():
            raise ValueError('Linked replacement refused')
        backup = out / (str(index) + '-' + target.name)
        shutil.copy2(target, backup)
        rows.append({'source': str(source), 'target': str(target), 'backup': str(backup),
                     'before': digest(target), 'after': digest(source)})
    (out / 'plan.json').write_text(json.dumps(rows, indent=2))
    for row in rows:
        target = Path(row['target'])
        assert digest(target) == row['before']
        shutil.copy2(row['source'], target)
        assert digest(target) == row['after']
    (out / 'result.json').write_text(json.dumps({'installed': rows, 'plugin_rebuilt': False}, indent=2))
    print(out)


if __name__ == '__main__':
    main()
