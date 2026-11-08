import json
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from core import client as protocol
from server.app import create_app
from server.scheduling import bounds, dates, ensure_plans, random_times, validate
from server.storage import Store, DEFAULTS
from server.worker import Worker

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()
PASSWORD = 'Local-test-password-12345'


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr('time.time', lambda: NOW)
    return create_app({'ADMIN_PASSWORD': PASSWORD, 'DATA_DIR': str(tmp_path), 'START_WORKER': False})


@pytest.fixture
def auth(app):
    browser = app.test_client()
    browser.get('/')
    with browser.session_transaction() as session:
        csrf = session['csrf']
    result = browser.post('/api/login', json={'username':'admin','password':PASSWORD}, headers={'X-CSRF-Token':csrf})
    assert result.status_code == 200
    with browser.session_transaction() as session:
        csrf = session['csrf']
    return browser, {'X-CSRF-Token': csrf}


def add(auth, number=1, **extra):
    browser, headers = auth
    payload = {'name':f'测试账号{number}', 'token':f'private-login-{number}', 'risk':f'private-risk-{number}'}
    payload.update(extra)
    response = browser.post('/api/accounts', json=payload, headers=headers)
    assert response.status_code == 201, response.json
    return response.json['id']


def test_auth_csrf_and_logout(app, auth):
    anonymous = app.test_client()
    assert anonymous.get('/api/dashboard').status_code == 401
    assert anonymous.post('/api/accounts', json={}).status_code == 403
    browser, headers = auth
    assert browser.get('/api/dashboard').status_code == 200
    assert browser.put('/api/settings', json={'mode':'window'}).status_code == 403
    assert browser.post('/api/logout', headers=headers).status_code == 200
    assert browser.get('/api/dashboard').status_code == 401


def test_weak_password_rejected(tmp_path):
    with pytest.raises(RuntimeError):
        create_app({'ADMIN_PASSWORD':'CHANGE_ME_USE_AT_LEAST_12_CHARACTERS','DATA_DIR':str(tmp_path)})


def test_login_rate_limit(app):
    browser = app.test_client()
    browser.get('/')
    with browser.session_transaction() as session:
        headers={'X-CSRF-Token': session['csrf']}
    for _ in range(5):
        assert browser.post('/api/login',json={'username':'admin','password':'wrong'},headers=headers).status_code == 401
    assert browser.post('/api/login',json={'username':'admin','password':PASSWORD},headers=headers).status_code == 429


def test_encrypted_credentials_and_no_api_leak(app,auth):
    add(auth)
    browser,headers=auth
    store=app.extensions['store']
    database=store.path.read_bytes()
    assert b'private-login-1' not in database and b'private-risk-1' not in database
    data=browser.get('/api/dashboard').data
    assert b'private-login-1' not in data and b'private-risk-1' not in data
    assert store.list_accounts(private=True)[0]['token']=='private-login-1'
    assert store.list_accounts()[0]['has_token']


def test_settings_window_and_minimum_interval(app,auth):
    ids=[add(auth,n) for n in range(1,5)]
    browser,headers=auth
    result=browser.put('/api/settings',json={'mode':'window','start':'13:00','end':'17:00','gap_minutes':30},headers=headers)
    assert result.status_code==200,result.json
    jobs=app.extensions['store'].rows("SELECT * FROM jobs WHERE day=? AND state='pending' ORDER BY run_at",('2026-11-07',))
    start,end=bounds('2026-11-07',{'mode':'window','start':'13:00','end':'17:00','timezone':'Asia/Shanghai'})
    assert len(jobs)==4
    assert all(start<=j['run_at']<end for j in jobs)
    assert all(b['run_at']-a['run_at']>=1800 for a,b in zip(jobs,jobs[1:]))
    assert {j['account_id'] for j in jobs}==set(ids)


def test_invalid_window_rolls_back_settings_and_plan(app,auth):
    for n in range(1,5):add(auth,n)
    browser,headers=auth
    store=app.extensions['store']
    old=store.settings()
    jobs=store.rows('SELECT * FROM jobs ORDER BY id')
    response=browser.put('/api/settings',json={'mode':'window','start':'13:00','end':'13:10','gap_minutes':15},headers=headers)
    assert response.status_code==400
    assert store.settings()==old
    assert store.rows('SELECT * FROM jobs ORDER BY id')==jobs


def test_plan_persists_and_next_day_is_distinct(app,auth):
    add(auth)
    store=app.extensions['store']
    before=store.rows('SELECT * FROM jobs ORDER BY day')
    reopened=Store(str(store.directory))
    with reopened.transaction() as db: ensure_plans(reopened,db,NOW)
    assert reopened.rows('SELECT * FROM jobs ORDER BY day')==before
    assert [r['day'] for r in before]==['2026-11-07','2026-11-08']
    assert before[0]['run_at']!=before[1]['run_at']


def test_missing_key_is_not_silently_replaced(app):
    store=app.extensions['store']
    (store.directory/'.key').unlink()
    with pytest.raises(RuntimeError):Store(str(store.directory))


def test_fingerprint_conflict_and_app_requirements(auth):
    add(auth)
    browser,headers=auth
    response=browser.post('/api/accounts',json={'name':'其他','token':'other','risk':'private-risk-1'},headers=headers)
    assert response.status_code==400
    response=browser.post('/api/accounts',json={'name':'其他','token':'other','risk':'other-risk','app_enabled':True},headers=headers)
    assert response.status_code==400


def test_edit_keeps_credentials_and_completed_job(app,auth):
    ident=add(auth)
    store=app.extensions['store']
    with store.transaction() as db:
        db.execute("UPDATE jobs SET state='success',finished=? WHERE day=? AND account_id=?",(NOW-100,'2026-11-07',ident))
    browser,headers=auth
    result=browser.put('/api/accounts/'+ident,json={'name':'新名称'},headers=headers)
    assert result.status_code==200
    assert store.list_accounts(private=True)[0]['token']=='private-login-1'
    assert store.rows("SELECT state FROM jobs WHERE day='2026-11-07'")[0]['state']=='success'
    assert browser.post('/api/accounts/'+ident+'/run',headers=headers).status_code==409


def test_bark_update_does_not_replan_or_expose_key(app,auth):
    add(auth)
    store=app.extensions['store']
    before=store.rows('SELECT run_at FROM jobs ORDER BY id')
    browser,headers=auth
    assert browser.put('/api/settings',json={'bark_key':'private-bark'},headers=headers).status_code==200
    assert before==store.rows('SELECT run_at FROM jobs ORDER BY id')
    assert b'private-bark' not in browser.get('/api/dashboard').data
    assert b'private-bark' not in store.path.read_bytes()
    assert store.decrypt(store.settings()['bark_key'])=='private-bark'


def make_due(store):
    with store.transaction() as db:
        db.execute("UPDATE jobs SET run_at=?,window_end=? WHERE day=? AND state='pending'",(NOW-1,NOW+3600,'2026-11-07'))


def test_claim_serialization_and_gap_after_finish(app,auth):
    add(auth,1);add(auth,2)
    store=app.extensions['store'];make_due(store)
    worker=Worker(store)
    claimed=worker.claim(NOW)
    assert claimed
    assert Worker(store).claim(NOW) is None
    with store.transaction() as db:
        db.execute("UPDATE jobs SET state='success',finished=? WHERE id=?",(NOW,claimed[0]['id']))
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('last_finish',str(NOW)))
    assert worker.claim(NOW+899) is None
    assert worker.claim(NOW+900)


def test_disabled_scheduler_and_manual_queue(app,auth):
    ident=add(auth)
    browser,headers=auth
    assert browser.put('/api/settings',json={'enabled':False},headers=headers).status_code==200
    store=app.extensions['store'];make_due(store)
    worker=Worker(store)
    assert worker.claim(NOW) is None
    assert browser.post('/api/accounts/'+ident+'/run',headers=headers).status_code==200
    assert worker.claim(NOW)


def test_worker_refreshes_persists_and_does_not_resign(app,auth,monkeypatch):
    ident=add(auth)
    store=app.extensions['store'];make_due(store)
    calls=[]
    monkeypatch.setattr(protocol,'refresh_token',lambda token:('rotated-private','续期成功'))
    def check(token,risk,activity):
        calls.append((token,risk,activity));return {'status':'success','message':'已签（日历确认）'}
    monkeypatch.setattr(protocol,'checkin',check)
    worker=Worker(store)
    monkeypatch.setattr(worker,'send',lambda *args:True)
    assert worker.tick(NOW)
    assert not worker.tick(NOW+10)
    assert calls==[('rotated-private','private-risk-1',protocol.MINI_ACTIVITY)]
    assert store.list_accounts(private=True)[0]['token']=='rotated-private'
    assert store.rows("SELECT notified FROM jobs WHERE day='2026-11-07'")[0]['notified']==1


def test_notification_retry_does_not_repeat_signup(app,auth,monkeypatch):
    add(auth);store=app.extensions['store'];make_due(store)
    monkeypatch.setattr(protocol,'refresh_token',lambda token:(None,'续期失败'))
    calls=[]
    monkeypatch.setattr(protocol,'checkin',lambda *args:calls.append(args) or {'status':'success','message':'ok'})
    worker=Worker(store);monkeypatch.setattr(worker,'send',lambda *args:False)
    worker.tick(NOW);worker.tick(NOW+301)
    assert len(calls)==1
    row=store.rows("SELECT * FROM jobs WHERE day='2026-11-07'")[0]
    assert row['notify_attempts']==2 and row['notified']==0


def test_expired_window_is_not_executed(app,auth,monkeypatch):
    add(auth);store=app.extensions['store']
    with store.transaction() as db:db.execute("UPDATE jobs SET run_at=?,window_end=? WHERE day='2026-11-07'",(NOW-100,NOW-1))
    worker=Worker(store)
    monkeypatch.setattr(worker,'execute',lambda account:pytest.fail('must not run expired job'))
    monkeypatch.setattr(worker,'send',lambda *args:True)
    assert not worker.tick(NOW)
    assert store.rows("SELECT state FROM jobs WHERE day='2026-11-07'")[0]['state']=='missed'


def test_worker_restart_marks_interrupted_unknown_and_locks(app,auth,monkeypatch):
    add(auth);store=app.extensions['store'];make_due(store)
    assert Worker(store).claim(NOW)
    monkeypatch.setattr(Worker,'loop',lambda self:None)
    worker=Worker(store);worker.start()
    try:
        assert store.rows("SELECT state FROM jobs WHERE day='2026-11-07'")[0]['state']=='unknown'
        with pytest.raises(RuntimeError):Worker(store).start()
    finally:
        worker.stop_event.set();worker.thread.join();worker.lock_file.close()


def test_time_window_validation_and_random_spacing():
    settings=dict(DEFAULTS,mode='window',start='08:00',end='10:00')
    validate(settings,4)
    for seed in range(50):
        times=random_times(0,7200,4,900,random.Random(seed))
        assert all(0<=x<7200 for x in times)
        assert all(b-a>=900 for a,b in zip(times,times[1:]))
    for update in ({'start':'22:00','end':'08:00'},{'timezone':'Not/AZone'},{'gap_minutes':0}):
        with pytest.raises(ValueError):validate(dict(settings,**update),4)


def test_health_and_page_assets(app,auth):
    browser,headers=auth
    for path in ('/','/static/app.js','/static/style.css','/static/logo.svg','/healthz'):
        response=browser.get(path)
        assert response.status_code==200
        assert response.headers['X-Frame-Options']=='DENY'
    assert b'ADMIN_PASSWORD' not in browser.get('/').data


def test_app_separate_credentials_encrypted_and_captcha_taken_once(app,auth,monkeypatch):
    ident=add(auth,app_enabled=True,app_token='private-app-login',app_risk='private-app-risk',app_captcha='private-manual-captcha')
    browser,headers=auth; store=app.extensions['store']; make_due(store)
    for secret in (b'private-app-login',b'private-app-risk',b'private-manual-captcha'):
        assert secret not in store.path.read_bytes()
        assert secret not in browser.get('/api/dashboard').data
    assert browser.put('/api/accounts/'+ident,json={'app_captcha':'undefined'},headers=headers).status_code==400
    assert browser.put('/api/accounts/'+ident,json={'app_token':'bad\nheader'},headers=headers).status_code==400
    worker=Worker(store); job,account=worker.claim(NOW)
    assert account['app_captcha']=='private-manual-captcha'
    assert store.list_accounts(private=True)[0]['app_captcha']==''
    monkeypatch.setattr(protocol,'refresh_token',lambda token:('rotated-mini','mini refreshed'))
    calls=[]
    def check(token,risk,activity,**kwargs):
        calls.append((token,risk,activity,kwargs)); return {'status':'success','message':'ok'}
    monkeypatch.setattr(protocol,'checkin',check)
    monkeypatch.setattr(worker.stop_event,'wait',lambda seconds:False)
    assert worker.execute(account)[0]=='success'
    assert calls==[('rotated-mini','private-risk-1',protocol.MINI_ACTIVITY,{}),
                   ('private-app-login','private-app-risk',protocol.APP_ACTIVITY,{'captcha':'private-manual-captcha'})]
    assert store.list_accounts(private=True)[0]['app_token']=='private-app-login'


def test_legacy_database_migrates_without_reusing_mini_login(tmp_path,monkeypatch):
    import sqlite3
    from cryptography.fernet import Fernet
    key=Fernet.generate_key(); (tmp_path/'.key').write_bytes(key)
    encrypt=lambda value:Fernet(key).encrypt(value.encode()).decode()
    db=sqlite3.connect(tmp_path/'longfor.db')
    db.execute('''CREATE TABLE accounts(id TEXT PRIMARY KEY,name TEXT NOT NULL,token TEXT NOT NULL,
        risk TEXT NOT NULL,app_risk TEXT NOT NULL,enabled INTEGER NOT NULL,app_enabled INTEGER NOT NULL,
        updated REAL NOT NULL,refreshed REAL)''')
    db.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?,?)',('old','旧账号',encrypt('mini'),encrypt('risk'),encrypt('app-risk'),1,1,NOW,None))
    db.commit();db.close()
    store=Store(tmp_path); account=store.list_accounts(private=True)[0]
    assert account['app_token']==account['app_captcha']==''
    assert account['token']=='mini' and (tmp_path/'.key').read_bytes()==key
    monkeypatch.setattr(protocol,'refresh_token',lambda token:(None,'not refreshed'))
    calls=[]
    monkeypatch.setattr(protocol,'checkin',lambda *args,**kwargs:calls.append(args) or {'status':'success','message':'ok'})
    state,message,details=Worker(store).execute(account)
    assert state=='partial' and len(calls)==1 and calls[0][2]==protocol.MINI_ACTIVITY
    assert 'APP 登录 token' in details['app']['message']
    assert Store(tmp_path).list_accounts(private=True)[0]['token']=='mini'


def test_per_client_user_agents_persist_and_reach_worker(app,auth,monkeypatch):
    ident=add(auth,app_enabled=True,app_token='private-app-login',app_risk='private-app-risk',mini_user_agent='Captured mini UA',app_user_agent='Captured app UA')
    browser,headers=auth;store=app.extensions['store']
    account=store.list_accounts(private=True)[0]
    assert b'Captured mini UA' not in store.path.read_bytes()
    assert browser.put('/api/accounts/'+ident,json={'mini_user_agent':'','app_user_agent':''},headers=headers).status_code==200
    assert store.list_accounts(private=True)[0]['app_user_agent']=='Captured app UA'
    assert browser.put('/api/accounts/'+ident,json={'app_user_agent':'bad\nheader'},headers=headers).status_code==400
    refreshed=[];calls=[]
    def refresh(token,**kwargs):refreshed.append(kwargs);return ('mini-new','ok')
    def check(token,risk,activity,**kwargs):calls.append((token,activity,kwargs));return {'status':'success','message':'ok'}
    monkeypatch.setattr(protocol,'refresh_token',refresh);monkeypatch.setattr(protocol,'checkin',check)
    worker=Worker(store);monkeypatch.setattr(worker.stop_event,'wait',lambda seconds:False)
    assert worker.execute(account)[0]=='success'
    assert refreshed==[{'user_agent':'Captured mini UA'}]
    assert calls==[('mini-new',protocol.MINI_ACTIVITY,{'user_agent':'Captured mini UA'}),
                   ('private-app-login',protocol.APP_ACTIVITY,{'captcha':'','user_agent':'Captured app UA'})]
