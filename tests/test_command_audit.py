"""Exercise the real command processing method without importing native CARLA."""
import ast
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('failure', ['intent','completion',None])
def test_audit_failure_boundaries(tmp_path, failure):
    source = Path(__file__).resolve().parents[1]/'src/carla_safety_agent/evaluation_control.py'
    tree = ast.parse(source.read_text())
    cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EvaluationControl')
    method = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_process_commands')
    env = {'json':json,'os':os,'time':time,'carla':SimpleNamespace(World=object)}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),env)
    (tmp_path/'commands').mkdir()
    command = tmp_path/'commands/cmd.json'
    command.write_text(json.dumps({'action':'move','payload':{'x':12}}))
    records, executed = [], []
    def write(path, record):
        if path.parent.name=='audit':
            if (failure=='intent' and record['state']=='attempting') or (failure=='completion' and record['state']=='responded'):
                raise OSError('disk full')
            records.append(record)
    control = SimpleNamespace(root=tmp_path,audit_dir=tmp_path/'audit',_atomic_json=write,
                              _execute=lambda *args:executed.append(args) or {'moved':True})
    world = SimpleNamespace(get_snapshot=lambda:SimpleNamespace(frame=42))
    if failure:
        with pytest.raises(OSError): env['_process_commands'](control,world)
        assert command.exists()
    else:
        env['_process_commands'](control,world)
        assert not command.exists()
    assert len(executed)==(0 if failure=='intent' else 1)
    if failure=='completion': assert records[-1]['state']=='attempting'
    if failure is None:
        assert records[-1]['state']=='responded' and records[-1]['response']['ok']
        assert records[-1]['observed_frame_after']==42
