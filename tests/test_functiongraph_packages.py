import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import types
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from scripts.build_functiongraph import build

ROOT=Path(__file__).resolve().parents[1]


def test_both_functiongraph_variants_build_separately(tmp_path):
    products=build(ROOT,tmp_path,'v1.0.0')
    assert len(products)==4
    for mode in ('fixed','random'):
        source=ROOT/'cloud_function'/mode
        code=tmp_path/f'longfor-sign-functiongraph-{mode}-code-v1.0.0.zip'
        bundle=tmp_path/f'longfor-sign-functiongraph-{mode}-v1.0.0.zip'
        with ZipFile(bundle) as archive:
            assert set(archive.namelist())=={'functiongraph.yml','main.zip'}
            assert archive.read('main.zip')==code.read_bytes()
            template=archive.read('functiongraph.yml').decode()
            assert f'longfor-sign-{mode}:' in template
            assert 'CodeFileName: main.zip' in template
            assert "LONGFOR_TOKENS_JSON: '[]'" in template
            assert "BARK_KEY: ''" in template
        with ZipFile(code) as archive:
            assert 'main.py' in archive.namelist()
            assert ('state_store.py' in archive.namelist())==(mode=='random')
            for name in archive.namelist():
                assert name.endswith('.py') or name=='requirements.txt'
                expected=(source/name) if (source/name).exists() else ROOT/name
                assert archive.read(name)==expected.read_bytes()
                if name.endswith('.py'):compile(archive.read(name),name,'exec')
            assert 'core/client.py' in archive.namelist()
            assert 'core/captcha.py' in archive.namelist()
    sums=(tmp_path/'SHA256SUMS').read_text()
    assert all(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' in sums for p in products)
    previous={p.name:p.read_bytes() for p in products}
    build(ROOT,tmp_path,'v1.0.0')
    assert previous=={p.name:p.read_bytes() for p in products}


@pytest.mark.parametrize('version',['../bad','x/y','', 'x y'])
def test_package_version_cannot_escape_output(tmp_path,version):
    with pytest.raises(ValueError):build(ROOT,tmp_path,version)


def test_fixed_entry_runs_all_accounts_without_scheduler(monkeypatch,tmp_path):
    monkeypatch.delenv("SIGN_OBS_BUCKET",raising=False)
    monkeypatch.setenv("SIGN_STATE_DIR",str(tmp_path))
    sign=Mock(return_value=(True,'已完成',4,4));notify=Mock(return_value=True)
    monkeypatch.setitem(sys.modules,'longfor',types.SimpleNamespace(longfor_sign=sign))
    monkeypatch.setitem(sys.modules,'bark_notify',types.SimpleNamespace(notify_sign_result=notify))
    spec=importlib.util.spec_from_file_location('fixed_entry_test',ROOT/'cloud_function/fixed/main.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.main({},None)
    assert result['success'] and result['success_count']==4 and result['total_count']==4
    assert sign.call_count==1
    assert sign.call_args.kwargs['store'].directory==tmp_path
    notify.assert_called_once_with(['已完成'],True,4,4)
    sign.side_effect=RuntimeError('sensitive-response')
    assert module.main({},None)['message']=='固定触发签到异常：RuntimeError'


@pytest.mark.parametrize('mode',['fixed','random'])
def test_code_zip_runs_without_repository_modules(tmp_path,mode):
    import json
    import os
    import subprocess
    build(ROOT,tmp_path,'dev')
    target=tmp_path/mode;target.mkdir()
    with ZipFile(tmp_path/f'longfor-sign-functiongraph-{mode}-code-dev.zip') as archive:
        archive.extractall(target)
    env={k:v for k,v in os.environ.items() if not k.startswith(('LONGFOR_','SIGN_','BARK_','PYTHONPATH'))}
    env.update(LONGFOR_TOKENS_JSON=json.dumps(['mini-'+str(i) for i in range(4)]),
               LONGFOR_DXRISK_TOKENS_JSON=json.dumps(['risk-'+str(i) for i in range(4)]),
               SIGN_APP_ACCOUNT_IDS_JSON='["account-1"]',LONGFOR_APP_TOKENS_JSON='["app-login","","",""]',
               LONGFOR_APP_DXRISK_TOKENS_JSON='["app-risk","","",""]',
               LONGFOR_APP_USER_AGENTS_JSON='["app-ua","","",""]',SIGN_STATE_DIR=str(target/'state'),
               SIGN_START_DELAY_MAX_SECONDS='0',SIGN_ACCOUNT_INTERVAL_MIN_SECONDS='1',SIGN_ACCOUNT_INTERVAL_MAX_SECONDS='1')
    program="\nimport json,os,sys\nfrom unittest.mock import patch\nfrom pathlib import Path\nfrom core.file_store import FileStore\ncalls=[]\ndef check(token,risk,activity,**kwargs):\n    calls.append((token,risk,activity,kwargs))\n    return {'status':'success','message':'verified'}\nwith patch('core.client.refresh_token',side_effect=lambda token,**kw:('fresh-'+token,'ok')),patch('core.client.checkin',side_effect=check),patch('time.sleep'),patch('requests.Session',side_effect=AssertionError('Unexpected network')):\n    import main\n    if sys.argv[1]=='random':\n        import daily_scheduler as scheduler\n        make=scheduler.make_plan\n        def plan(day,accounts):\n            result=make(day,accounts)\n            for i,item in enumerate(result['accounts']):item.update(slot=i*2,jitter=0)\n            return result\n        with patch.object(scheduler,'make_plan',side_effect=plan),patch.object(main,'run',side_effect=lambda context:scheduler.run(context,store=FileStore(os.environ['SIGN_STATE_DIR']),now=scheduler.datetime(2026,11,8,12,tzinfo=scheduler.CST))):\n            result=main.main({},None)\n    else:\n        result=main.main({},None)\n    assert result['status']=='success',result\n    app=[c for c in calls if c[2]=='11111111111736501868255956070000']\n    assert len(app)==1 and app[0][0]=='app-login' and app[0][3]['user_agent']=='app-ua',calls\n    assert all(c[0].startswith('fresh-') for c in calls if c not in app)\n"
    result=subprocess.run([sys.executable,'-c',program,mode],cwd=target,env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
