"""One environment schema for scripts, Actions and both FunctionGraph entries."""
import json
import os


def load_tokens_json(key):
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return []
    try:
        values = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError(key+' 必须是 JSON 字符串数组') from None
    if not isinstance(values,list) or not all(isinstance(v,str) for v in values):
        raise ValueError(key+' 必须是 JSON 字符串数组')
    return [v.strip() for v in values]


def _values(key, legacy):
    if os.environ.get(key,'').strip():
        return load_tokens_json(key)
    return [v.strip() for v in os.environ.get(legacy,'').splitlines() if v.strip()]


def _optional(key, count, default=''):
    values = load_tokens_json(key) if os.environ.get(key,'').strip() else [default]*count
    if len(values)!=count:
        raise ValueError(key+' 的长度必须与账号数量一致，未配置位置填空字符串')
    return values


def load_accounts():
    tokens=_values('LONGFOR_TOKENS_JSON','LONGFOR_TOKEN')
    risks=_values('LONGFOR_DXRISK_TOKENS_JSON','LONGFOR_DXRISK_TOKEN')
    if not tokens or len(tokens)!=len(risks) or not all(tokens) or not all(risks):
        raise ValueError('请配置一一对应且非空的登录 token 和小程序风控 token')
    count=len(tokens)
    ids=load_tokens_json('SIGN_ACCOUNT_IDS_JSON') if os.environ.get('SIGN_ACCOUNT_IDS_JSON','').strip() else [f'account-{i+1}' for i in range(count)]
    names=load_tokens_json('SIGN_ACCOUNT_NAMES_JSON') if os.environ.get('SIGN_ACCOUNT_NAMES_JSON','').strip() else [f'账号{i+1}' for i in range(count)]
    if len(ids)!=count or len(set(ids))!=count or not all(ids) or len(names)!=count or not all(names):
        raise ValueError('账号标识和名称须与账号数量一致，标识必须唯一且非空')
    enabled=load_tokens_json('SIGN_APP_ACCOUNT_IDS_JSON')
    if len(set(enabled))!=len(enabled) or any(ident not in ids for ident in enabled):
        raise ValueError('SIGN_APP_ACCOUNT_IDS_JSON 必须由已配置且不重复的账号标识组成')
    app_tokens=_optional('LONGFOR_APP_TOKENS_JSON',count)
    app_risks=_optional('LONGFOR_APP_DXRISK_TOKENS_JSON',count)
    mini_uas=_optional('LONGFOR_MINI_USER_AGENTS_JSON',count,os.environ.get('LONGFOR_USER_AGENT','').strip())
    app_uas=_optional('LONGFOR_APP_USER_AGENTS_JSON',count,os.environ.get('LONGFOR_APP_USER_AGENT','').strip())
    accounts=[]; token_owners={}; risk_owners={}
    for i,ident in enumerate(ids):
        account=dict(id=ident,name=names[i],token=tokens[i],risk=risks[i],app_token=app_tokens[i],
                     app_risk=app_risks[i],mini_user_agent=mini_uas[i],app_user_agent=app_uas[i],
                     app_captcha='',enabled=True,app_enabled=ident in enabled)
        if account['app_enabled'] and (not app_tokens[i] or not app_risks[i]):
            raise ValueError('开启 APP 的账号必须配置独立的 APP 登录 token 和 APP 风控 token')
        for key in ('token','risk','app_token','app_risk','mini_user_agent','app_user_agent'):
            value=account[key]
            if key.endswith('user_agent') and len(value)>1024:
                raise ValueError('User-Agent 最多 1024 字符')
            if len(value)>4096 or any(ord(c)<32 or ord(c)>126 for c in value):
                raise ValueError('请求头配置必须是不含换行的 ASCII 文本，长度不超过 4096')
        for value in (tokens[i],app_tokens[i]):
            if value and value in token_owners and token_owners[value]!=ident:
                raise ValueError('不同账号不能共用登录 token')
            if value: token_owners[value]=ident
        for value in (risks[i],app_risks[i]):
            if value and value in risk_owners and risk_owners[value]!=ident:
                raise ValueError('不同账号不能共用风控 token')
            if value:risk_owners[value]=ident
        accounts.append(account)
    return accounts
