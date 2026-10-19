import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from carla_safety_agent.dataset_jobs import start_dataset_job


class Service:
    def __init__(self):self.lock=threading.RLock();self.active=None
    def start(self,payload):
        with self.lock:
            self.active=payload
            return payload


def test_competing_service_starts_only_one():
    services={key:Service() for key in ('archive','recovery')}
    barrier=threading.Barrier(2)
    def call(name):
        barrier.wait(timeout=3)
        try:return start_dataset_job(services,name,name)
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(call,key) for key in services]
        values=[future.result(timeout=3) for future in futures]
    assert values.count('rejected')==1
    winner=next(value for value in values if value!='rejected')
    assert start_dataset_job(services,winner,winner)==winner
    services[winner].active=None
    assert start_dataset_job(services,'recovery','new')=='new'


def test_exception_releases_peer_locks():
    services={'a':Service(),'b':Service()}
    def fail(_):raise ValueError('invalid')
    services['a'].start=fail
    with pytest.raises(ValueError):start_dataset_job(services,'a',{})
    assert start_dataset_job(services,'b','valid')=='valid'
