"""Verify real Blender retains an inherited lock without creating scene assets."""
import fcntl
import json
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix='csa-blender-lock-') as temporary:
        path = Path(temporary) / 'admission.lock'
        parent = path.open('a')
        fcntl.flock(parent, fcntl.LOCK_SH | fcntl.LOCK_NB)
        descriptor = parent.fileno()
        expression = (
            'import os,sys,bpy; '
            f'os.fstat({descriptor}); '
            'print("CSA_LOCK_READY:"+bpy.app.version_string,flush=True); '
            'sys.stdin.readline()')
        child = subprocess.Popen([
            os.environ.get('BLENDER_BIN', '/snap/bin/blender'), '--background',
            '--factory-startup', '--python-exit-code', '7', '--python-expr', expression],
            pass_fds=(descriptor,), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        parent.close()  # Only the real external program can now retain the lock.
        try:
            output = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                deadline = time.monotonic() + 40
                while b'CSA_LOCK_READY:' not in output:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Blender readiness timeout: ' + output.decode(errors='replace'))
                    for key, _ in selector.select(timeout=1):
                        chunk = os.read(key.fileobj.fileno(), 4096)
                        if not chunk:
                            raise RuntimeError('Blender exited before readiness: ' + output.decode(errors='replace'))
                        output.extend(chunk)
            assert child.poll() is None, 'Blender must still be waiting'
            with path.open('a') as contender:
                try:
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    raise AssertionError('Blender did not retain shared admission lock')
                tail, _ = child.communicate(input=b'finish\n', timeout=20)
                output.extend(tail)
                assert child.returncode == 0, output.decode(errors='replace')
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(json.dumps({'passed': True, 'executable': os.environ.get('BLENDER_BIN', '/snap/bin/blender'),
                'parent_descriptor_closed': True, 'live_child_blocks_exclusive': True,
                'child_returncode': child.returncode, 'exit_releases_lock': True,
                'output': output.decode(errors='replace')}, ensure_ascii=False))
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=5)


if __name__ == '__main__':
    main()
