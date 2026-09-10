"""Standalone capture owns resources before controls/listeners can fail."""
import argparse
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


@pytest.mark.parametrize('fail_register', [False, True])
def test_standalone_journals_vehicle_and_capture_before_use(tmp_path, fail_register):
    events = []
    actor = NS(id=42, type_id='vehicle.test', apply_control=lambda *_: events.append('control'))
    class Journal:
        def register(self, value):
            assert value is actor
            events.append('register')
            if fail_register:
                raise OSError('disk full')
    journal = Journal()
    world = NS(get_settings=lambda: NS(synchronous_mode=False),
        apply_settings=lambda *_: events.append('settings'),
        get_blueprint_library=lambda: NS(find=lambda *_: NS(set_attribute=lambda *_: None)),
        get_map=lambda: NS(get_spawn_points=lambda: [object()]),
        try_spawn_actor=lambda *_: actor, tick=lambda *_: 1)
    actor.get_control = lambda: None
    def destroy(commands, tick):
        assert commands == [42] and tick is False
        events.append('destroy')
        return [NS(error=None)]
    client = NS(set_timeout=lambda *_: None, get_world=lambda: world, apply_batch_sync=destroy)
    def capture(*args, **kwargs):
        assert kwargs['journal'] is journal and kwargs['client'] is client
        events.append('capture')
        return NS(process_frame=lambda *_: None, count=1, error=None, close=lambda: [])
    tree = ast.parse((Path(__file__).resolve().parents[1]/'tools/run_sensor_rig.py').read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    env = dict(argparse=argparse, ROOT=tmp_path, Path=Path,
        os=NS(getpid=lambda: 123, environ={'CSA_EVALUATION_CONTROL_DIR': str(tmp_path)}),
        time=NS(monotonic=lambda: 0), signal=NS(SIGINT=2,SIGTERM=15,signal=lambda *_: None),
        SessionJournal=lambda *_: NS(owned_pid=lambda: 123),
        journal_from_environment=lambda _: journal,
        carla=NS(Client=lambda *_: client, VehicleControl=lambda **_: None,
                 command=NS(DestroyActor=lambda actor_id: actor_id)),
        SensorCapture=capture, EvaluationControl=lambda *_: NS(on_frame=lambda *_: None),
        atomic_json=lambda *_: None, json=NS(dumps=lambda _: '{}'))
    exec(compile(ast.Module(body=[main], type_ignores=[]), '<sensor-rig>', 'exec'), env)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr('sys.argv', ['run_sensor_rig.py', '--frames', '10'])
        if fail_register:
            with pytest.raises(OSError, match='disk full'):
                env['main']()
            assert 'control' not in events and 'capture' not in events
        else:
            env['main']()
            assert events.index('register') < events.index('control') < events.index('capture')
    assert events[-2:] == ['destroy', 'settings']
