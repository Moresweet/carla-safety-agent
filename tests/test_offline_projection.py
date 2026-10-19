import json
import subprocess
from types import SimpleNamespace as NS
import numpy as np
import pytest
from carla_safety_agent.offline_projection import archived_prediction
from carla_safety_agent.map_projection_archive import archive_map_projection


def fixture(tmp_path):
    ref=archive_map_projection(tmp_path,NS(name='Town04',to_opendrive=lambda:'<OpenDRIVE><header><geoReference>+proj=tmerc</geoReference></header></OpenDRIVE>'))
    return {'map':'Town04','map_projection':ref}


def test_missing_archive_never_starts_worker(tmp_path,monkeypatch):
    def fail(*a,**k):raise AssertionError('No current-map fallback')
    monkeypatch.setattr(subprocess,'run',fail)
    assert archived_prediction(tmp_path,{}, {},np.eye(4))['state']=='unavailable'


@pytest.mark.parametrize('fault',['crash','timeout','malformed','wrong_map','points'])
def test_native_failure_remains_isolated(tmp_path,monkeypatch,fault):
    manifest=fixture(tmp_path)
    def run(*args,**kwargs):
        assert kwargs['timeout']==15
        if fault=='timeout':raise subprocess.TimeoutExpired(args[0],15)
        value={'state':'available','map_sha256':manifest['map_projection']['sha256'],
               'source_frame':1,'timing_verified':False,'error_metrics_computed':False,'points':[]}
        if fault=='wrong_map':value['map_sha256']='wrong'
        return NS(returncode=-11 if fault=='crash' else 0,stdout='bad' if fault=='malformed' else json.dumps(value))
    monkeypatch.setattr(subprocess,'run',run)
    result=archived_prediction(tmp_path,manifest,{'planning_anchor':{'frame':1}},np.eye(4))
    assert result['state']=='unavailable' and not result['points']
