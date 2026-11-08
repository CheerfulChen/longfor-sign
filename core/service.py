"""Shared account execution, refresh persistence and credential redaction."""
import hashlib
import time
from . import client


def execute(account, save_token=None, wait=None, stopped=None):
    wait=wait or time.sleep
    stopped=stopped or (lambda:False)
    old=account['token'];mini_ua=account.get('mini_user_agent')
    fresh,note=client.refresh_token(old,user_agent=mini_ua) if mini_ua else client.refresh_token(old)
    token=fresh or old
    if fresh and save_token:
        save_token(fresh)  # Fail closed before business requests if persistence fails.
    mini=client.checkin(token,account['risk'],client.MINI_ACTIVITY,**({'user_agent':mini_ua} if mini_ua else {}))
    app={'status':'off','message':'未开启'}
    if account.get('app_enabled'):
        if not account.get('app_token') or not account.get('app_risk'):
            app={'status':'failed','message':'请在账号设置中补充独立的 APP 登录 token 和风控 token；未发送 APP 请求'}
        else:
            wait(20)
            if stopped():
                app={'status':'unknown','message':'服务停止，APP 入口未继续执行'}
            else:
                app=client.checkin(account['app_token'],account['app_risk'],client.APP_ACTIVITY,
                                   captcha=account.get('app_captcha',''),
                                   **({'user_agent':account['app_user_agent']} if account.get('app_user_agent') else {}))
    states=[mini['status']]+([app['status']] if account.get('app_enabled') else [])
    status=('success' if all(s=='success' for s in states) else 'partial' if 'success' in states
            else 'risk' if 'risk' in states else 'unknown' if 'unknown' in states else 'failed')
    secrets=[old,token,account.get('risk'),account.get('app_risk'),account.get('app_token'),account.get('app_captcha')]
    def clean(value):
        if isinstance(value,str):
            for secret in sorted(filter(None,secrets),key=len,reverse=True):value=value.replace(secret,'[已隐藏]')
            return value[:3000]
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    message=note+'\n小程序：'+mini['message']
    if account.get('app_enabled'):message+='\nAPP：'+app['message']
    return clean(dict(status=status,message=message,refresh_success=bool(fresh),refresh=note,mini=mini,app=app))


def execute_persisted(store, account, **kwargs):
    registry=store.load('credentials')
    if registry is None:registry={'version':1,'accounts':{}}
    if not isinstance(registry,dict) or registry.get('version')!=1 or not isinstance(registry.get('accounts'),dict):
        raise ValueError('凭据文件格式不兼容')
    ident=account['id'];seed=hashlib.sha256(account['token'].encode()).hexdigest()
    entry=registry['accounts'].get(ident)
    if not isinstance(entry,dict) or entry.get('configured_token_hash')!=seed:
        entry={'configured_token_hash':seed,'token':account['token']}
    if not isinstance(entry.get('token'),str) or not entry['token']:
        raise ValueError('保存的登录凭据无效')
    registry['accounts'][ident]=entry
    store.save('credentials',registry)
    runtime=dict(account,token=entry['token'])
    def save(token):
        entry.update(token=token,refreshed_at=time.time())
        store.save('credentials',registry)
    return execute(runtime,save_token=save,**kwargs)
