"""Refresh login credentials and verify independent check-in activities.

Protocol reference: ken861222/longhu-checkin, commit
4fc54bbbd98d624aaa4d30d994289d5e83541df9. No requests run on import.
"""
import base64
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = 'https://gw2c-hw-open.longfor.com'
MINI_ACTIVITY = '11111111111686241863606037740000'
APP_ACTIVITY = '11111111111736501868255956070000'
SIGN_SECRET = 'Q74eKtH5LePYfSjIiflUbCL2gxjTa7rF'
MAIN_KEY = 'c06753f1-3e68-437d-b592-b94656ea5517'
WALLET_KEY = 'f4a2290e-c382-45b7-949c-3253d07e9b5b'
CST = timezone(timedelta(hours=8))
USER_AGENT = ('Mozilla/5.0 (iPhone; CPU iPhone OS 27_3 like Mac OS X) '
              'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 '
              'MicroMessenger/8.0.80(0x18005030) NetType/WIFI Language/zh_CN '
              'miniProgram/wx50282644351869da')


def _request(path, headers, body):
    # Do not log responses: some endpoints return login credentials.
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(BASE + path, headers=headers, json=body,
                                    timeout=(5, 10), allow_redirects=False)
        if response.status_code != 200:
            return {'code': 'HTTP_{}'.format(response.status_code)}
        try:
            value = response.json()
        except ValueError:
            value = json.loads(base64.b64decode(response.text, validate=True).decode('utf-8'))
        return value if isinstance(value, dict) else {'code': 'INVALID_RESPONSE'}
    except (requests.RequestException, ValueError, UnicodeError):
        return {'code': 'REQUEST_OR_RESPONSE_ERROR'}


def refresh_token(token, user_agent=None):
    timestamp = str(int(time.time() * 1000))
    signature = hashlib.md5((timestamp + '&' + SIGN_SECRET).encode()).hexdigest()
    headers = {'lmToken': token, 'X-LF-Bucode': 'C20400', 'X-LF-Channel': 'C2',
               'X-LF-Api-Version': 'v2_6_0', 'X-LF-App-Version': '2.6.0',
               'X-LONGZHU-TimeStamp': timestamp, 'X-LONGZHU-Sign': signature,
               'X-Client-Type': 'microApp', 'User-Agent': user_agent or USER_AGENT,
               'Origin': 'https://longzhu.longfor.com', 'Referer': 'https://longzhu.longfor.com/',
               'Content-Type': 'application/json'}
    first = _request('/supera/mine/v2_6_0/token/token2key', headers, {})
    data = first.get('data')
    key = data.get('key') if isinstance(data, dict) else None
    if not isinstance(key, str) or not key:
        return None, 'token2key 未返回有效 key，旧会话可能失效或接口暂不可用'
    second = _request('/lmember-lpns-api-prod/api/lpns/auth/v1/key2token',
                      {'X-Gaia-Api-Key': WALLET_KEY, 'systype': 'WALLET',
                       'User-Agent': user_agent or USER_AGENT, 'Content-Type': 'application/json',
                       'Origin': 'https://longball.longhu.net', 'Referer': 'https://longball.longhu.net/'},
                      {'key': key, 'buCode': 'C20400', 'channel': 'C2'})
    data = second.get('data')
    if str(second.get('code')) != '0000' or not isinstance(data, dict):
        return None, 'key2token 未返回有效登录凭据'
    new_token = data.get('token')
    if not isinstance(new_token, str) or not new_token.strip():
        return None, 'key2token 未返回有效登录凭据'
    # Do not invent a 30-day lifetime; the server remains the authority.
    return new_token.strip(), '登录 token 续期成功'


APP_USER_AGENT = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) '
                  'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 '
                  '&MAIAWebKit_iOS_com.longfor.supera_1.30.2_202610281019_Default_3.3.1.0')


def task_headers(token, risk, activity=MINI_ACTIVITY, captcha='', user_agent=None):
    is_app = activity == APP_ACTIVITY
    headers = {'token': token, 'X-LF-UserToken': token, 'X-LF-Bu-Code': 'L00602' if is_app else 'C20400',
            'X-LF-Channel': 'L0' if is_app else 'C2', 'X-GAIA-API-KEY': MAIN_KEY,
            'X-LF-DXRisk-Source': '2' if is_app else '5', 'X-LF-DXRisk-Token': risk,
            'Content-Type': 'application/json;charset=UTF-8', 'User-Agent': user_agent or (APP_USER_AGENT if is_app else USER_AGENT),
            'Origin': 'https://longzhu.longfor.com', 'Referer': 'https://longzhu.longfor.com/'}

    if captcha and captcha.lower() != 'undefined':
        headers['X-LF-DXRisk-Captcha-Token'] = captcha
    return headers


def sign_state(token, risk, activity, user_agent=None):
    response = _request('/lmarketing-task-api-mvc-prod/openapi/task/v1/signature/page-info',
                        task_headers(token, risk, activity, user_agent=user_agent), {'activity_no': activity})
    if str(response.get('code')) != '0000' or not isinstance(response.get('data'), dict):
        return None
    data = response['data']
    today = datetime.now(CST).date()
    try:
        if data.get('current_date_time'):
            today = datetime.fromtimestamp(int(data['current_date_time']) / 1000, CST).date()
        for entry in data.get('seven_days_signs') or []:
            if (int(entry['sign_year']), int(entry['sign_month']), int(entry['sign_day'])) == (
                    today.year, today.month, today.day):
                status = int(entry.get('sign_status', 0))
                return True if status == 20 else False if status == 10 else None
    except (ValueError, TypeError, KeyError, OverflowError, OSError):
        return None
    return None


def solve_captcha(user_agent, is_app):
    from .captcha import solve
    return solve(user_agent, is_app)


def checkin(token, risk, activity, captcha='', user_agent=None, auto_captcha=True):
    def calendar():
        return sign_state(token, risk, activity, user_agent=user_agent) if user_agent else sign_state(token, risk, activity)
    before = calendar()
    if before is True:
        return {'status': 'success', 'message': '今日已签（日历确认）'}
    if before is None:
        return {'status': 'failed', 'message': '签到日历查询失败，未发送签到请求；请检查凭据和风控状态'}
    response = _request('/lmarketing-task-api-mvc-prod/openapi/task/v1/signature/clock',
                        task_headers(token, risk, activity, captcha, user_agent), {'activity_no': activity})
    after = calendar()
    attempted_verification = False
    if after is False and auto_captcha and str(response.get('code')) in {'8040012','8040016'}:
        attempted_verification = True
        ua = user_agent or (APP_USER_AGENT if activity == APP_ACTIVITY else USER_AGENT)
        verified = solve_captcha(ua, activity == APP_ACTIVITY)
        if verified:
            # Recheck before replay: another client may have signed during verification.
            ready = calendar()
            if ready is True:
                return {'status':'success','message':'今日已签（验证后日历确认），未重复提交'}
            if ready is None:
                return {'status':'unknown','message':'验证后日历查询失败，未重新提交签到；请核实客户端记录'}
            response = _request('/lmarketing-task-api-mvc-prod/openapi/task/v1/signature/clock',
                                task_headers(token, risk, activity, verified, user_agent), {'activity_no':activity})
            after = calendar()
    if after is True:
        data = response.get('data')
        rewards = data.get('reward_info') if isinstance(data, dict) else None
        numbers = [str(x['reward_num']) for x in (rewards or []) if isinstance(x, dict) and 'reward_num' in x]
        return {'status': 'success', 'message': '签到成功（日历确认）' + ('，奖励数量 ' + ', '.join(numbers) if numbers else '')}
    if after is None:
        return {'status': 'unknown', 'message': '签到请求已发送，日历复核失败，结果待确认；不自动重试'}
    code = str(response.get('code', 'unknown'))
    # Restrict reflected fields to short error codes; do not expose response text.
    code = code if re.fullmatch(r'[A-Za-z0-9_]{1,40}', code) else 'unknown'
    if code in {'801810', '801811', '801812', '8040012', '8040016'}:
        return {'status': 'risk', 'message': ('自动验证未能完成签到（code={}），请在对应客户端核实或验证；本次不再重试' if attempted_verification else '需要人工核实或验证（code={}），请在对应客户端完成验证').format(code)}
    return {'status': 'failed', 'message': '日历仍显示未签（接口 code={}）；请检查活动资格、凭据或风控'.format(code)}
