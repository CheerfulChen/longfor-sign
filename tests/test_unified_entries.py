import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
from core import accounts, client, service, batch
from core.file_store import FileStore

ROOT=Path(__file__).resolve().parents[1]


class MemoryStore:
    def __init__(self):self.data={}
    def load(self,key):return copy.deepcopy(self.data.get(key))
    def save(self,key,value):self.data[key]=copy.deepcopy(value)


@pytest.fixture
def configured(monkeypatch):
    for key in list(os.environ):
        if key.startswith(('LONGFOR_','SIGN_','BARK_')):monkeypatch.delenv(key)
    monkeypatch.setenv('LONGFOR_TOKENS_JSON',json.dumps(['mini-'+str(i) for i in range(4)]))
    monkeypatch.setenv('LONGFOR_DXRISK_TOKENS_JSON',json.dumps(['risk-'+str(i) for i in range(4)]))
    monkeypatch.setenv('SIGN_APP_ACCOUNT_IDS_JSON','["account-1"]')
    monkeypatch.setenv('LONGFOR_APP_TOKENS_JSON','["app-0","","",""]')
    monkeypatch.setenv('LONGFOR_APP_DXRISK_TOKENS_JSON','["app-risk-0","","",""]')
    monkeypatch.setenv('LONGFOR_MINI_USER_AGENTS_JSON','["mini-ua","","",""]')
    monkeypatch.setenv('LONGFOR_APP_USER_AGENTS_JSON','["app-ua","","",""]')
    return accounts.load_accounts()


def test_legacy_and_json_settings_and_distinct_app_login(configured,monkeypatch):
    assert len(configured)==4 and configured[0]['app_token']=='app-0'
    monkeypatch.setenv('LONGFOR_APP_TOKENS_JSON','["","","",""]')
    with pytest.raises(ValueError,match='独立'):accounts.load_accounts()
    monkeypatch.setenv('SIGN_APP_ACCOUNT_IDS_JSON','[]')
    monkeypatch.setenv('LONGFOR_TOKENS_JSON','')
    monkeypatch.setenv('LONGFOR_DXRISK_TOKENS_JSON','')
    monkeypatch.setenv('LONGFOR_TOKEN','a\nb\nc\nd')
    monkeypatch.setenv('LONGFOR_DXRISK_TOKEN','r1\nr2\nr3\nr4')
    assert [a['token'] for a in accounts.load_accounts()]==['a','b','c','d']


def test_shared_registry_retains_refreshed_token(configured,monkeypatch,tmp_path):
    store=FileStore(tmp_path)
    refresh=Mock(side_effect=[('rotated-1','ok'),('rotated-2','ok')])
    monkeypatch.setattr(client,'refresh_token',refresh)
    check=Mock(return_value={'status':'success','message':'ok'})
    monkeypatch.setattr(client,'checkin',check)
    service.execute_persisted(store,configured[0],wait=lambda _:None)
    service.execute_persisted(store,configured[0],wait=lambda _:None)
    assert [c.args[0] for c in refresh.call_args_list]==['mini-0','rotated-1']
    assert store.load('credentials')['accounts']['account-1']['token']=='rotated-2'
    assert [c.args[0] for c in check.call_args_list]==['rotated-1','app-0','rotated-2','app-0']
    assert check.call_args_list[1].kwargs['user_agent']=='app-ua'
    assert store._path('credentials').stat().st_mode&0o777==0o600


def test_persistence_failure_stops_business_requests(configured,monkeypatch):
    store=MemoryStore();store.save=Mock(side_effect=RuntimeError('storage failure'))
    check=Mock();monkeypatch.setattr(client,'checkin',check)
    with pytest.raises(RuntimeError):service.execute_persisted(store,configured[0])
    check.assert_not_called()


def test_batch_shares_account_executor_and_preserves_pairing(configured,monkeypatch):
    calls=[]
    monkeypatch.setattr(batch,'execute_persisted',lambda store,account:calls.append(account) or {'status':'success','message':'ok'})
    monkeypatch.setattr(batch.time,'sleep',lambda _:None)
    result=batch.run(MemoryStore())
    assert result[0] and result[2:]==(4,4)
    assert {a['id'] for a in calls}=={a['id'] for a in configured}
    assert all(a['token'][-1]==a['risk'][-1] for a in calls)


@pytest.mark.parametrize('outcome',['success','risk'])
def test_random_entry_uses_shared_app_flow_and_terminal_state(configured,monkeypatch,outcome):
    folder=ROOT/'cloud_function/random'
    def load(name):
        spec=importlib.util.spec_from_file_location(name,folder/(name+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        monkeypatch.setitem(sys.modules,name,module);return module
    load('account_service');load('state_store');scheduler=load('daily_scheduler')
    monkeypatch.setattr(scheduler.time,'sleep',lambda _:None)
    monkeypatch.setattr(scheduler,'send_bark_notification',lambda *a,**kw:True)
    original=scheduler.make_plan
    def plan(day,triples):
        value=original(day,triples)
        for i,entry in enumerate(value['accounts']):entry.update(slot=i*2,jitter=0)
        return value
    monkeypatch.setattr(scheduler,'make_plan',plan)
    monkeypatch.setattr(client,'refresh_token',lambda *a,**kw:('rotated','ok'))
    check=Mock(return_value={'status':outcome,'message':'ok'});monkeypatch.setattr(client,'checkin',check)
    now=scheduler.datetime(2026,11,8,12,0,tzinfo=scheduler.CST);store=MemoryStore()
    result=scheduler.run(None,store=store,now=now)
    assert result['status']==outcome
    assert store.load('2026-11-08')['accounts'][0]['status']==outcome
    assert [c.args[0] for c in check.call_args_list]==['rotated','app-0']
    assert [c.kwargs['user_agent'] for c in check.call_args_list]==['mini-ua','app-ua']
    assert scheduler.run(None,store=store,now=now)['status']=='idle'
    assert check.call_count==2
