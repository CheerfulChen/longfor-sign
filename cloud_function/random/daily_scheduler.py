"""Half-hour polling, durable daily plans, at-most-once sign attempts.

Deployment MUST limit the function to one instance and one concurrent request.
"""
import hashlib
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone

from bark_notify import send_bark_notification
from core.accounts import load_accounts as load_environment
from account_service import account_ids, app_settings, execute_account
from state_store import ObsStore

CST = timezone(timedelta(hours=8))
TERMINAL = {'success', 'partial', 'failed', 'risk', 'unknown', 'missed'}


def load_accounts():
    configured=load_environment()
    if len(configured)!=4:raise ValueError('随机时间版当前要求 4 个账号')
    return [(a['token'],a['risk'],a['name']) for a in configured]


def make_plan(day, accounts):
    # Local Random avoids changing randomness used by captcha and request code.
    fingerprint = hashlib.sha256(json.dumps(account_ids()).encode()).hexdigest()
    # IDs identify accounts; installation-specific seed avoids identical schedules
    # across deployments that keep the default account IDs. Automatic refresh
    # updates OBS only, so environment seed tokens stay unchanged.
    seed = hashlib.sha256(json.dumps([a[0] for a in accounts]).encode()).hexdigest()
    rng = random.Random(hashlib.sha256((day + fingerprint + seed).encode()).digest())
    while True:
        slots = sorted(rng.sample(range(46), 4))  # 00:00..22:30; reserve late slots for catch-up.
        if all(b - a >= 2 for a, b in zip(slots, slots[1:])):
            break
    rng.shuffle(slots)
    entries = []
    for number, (account, slot) in enumerate(zip(accounts, slots)):
        entries.append({'index': number, 'account_id': account_ids()[number], 'name': account[2], 'slot': slot,
                        'jitter': rng.randint(10, 90), 'status': 'pending', 'message': ''})
    return {'version': 2, 'day': day, 'fingerprint': fingerprint, 'accounts': entries,
            'notified': [], 'plan_notified': False, 'summary_notified': False}


def clock_label(slot):
    return '{:02d}:{:02d}'.format(slot // 2, (slot % 2) * 30)


def redact(message, accounts):
    text = str(message)
    for token, risk, _ in accounts:
        text = text.replace(token, '[已隐藏]').replace(risk, '[已隐藏]')
    return text[:1800]


def progress(state):
    entries = state['accounts']
    success = sum(a['status'] == 'success' for a in entries)
    done = sum(a['status'] in TERMINAL for a in entries)
    return '成功 {}/4，已结束 {}/4'.format(success, done)


def notify_pending(store, state):
    """Notification failure does not undo sign results. Retry on later ticks."""
    day = state['day']
    if os.environ.get('SIGN_NOTIFY_PLAN', '0') == '1' and not state['plan_notified']:
        body = day + '（北京时间）\n' + '\n'.join(
            '{}：{} 后随机等待 {} 秒'.format(a['name'], clock_label(a['slot']), a['jitter'])
            for a in sorted(state['accounts'], key=lambda a: a['slot']))
        if send_bark_notification('📅 龙湖今日签到计划', body):
            state['plan_notified'] = True
            store.save(day, state)
    labels = {'success': '✅ 成功', 'partial': '⚠️ 部分成功', 'failed': '❌ 失败', 'risk': '⚠️ 需验证', 'unknown': '⚠️ 结果待确认', 'missed': '⚠️ 未执行'}
    for item in state['accounts']:
        marker = item['index']
        if item['status'] not in TERMINAL or marker in state['notified']:
            continue
        body = '{}（北京时间）\n计划：{}\n执行：{}\n{}\n{}'.format(
            day, clock_label(item['slot']), item.get('finished_at', '未执行'), item['message'], progress(state))
        if send_bark_notification('{} {} 龙湖签到'.format(labels[item['status']], item['name']), body):
            state['notified'].append(marker)
            store.save(day, state)
    if all(a['status'] in TERMINAL for a in state['accounts']) and not state['summary_notified']:
        lines = ['{}：{}；{}'.format(a['name'], labels[a['status']], a['message']) for a in state['accounts']]
        if send_bark_notification('📊 龙湖 {} 签到汇总 {}'.format(day, progress(state)), '\n'.join(lines)):
            state['summary_notified'] = True
            store.save(day, state)


def close_unfinished(state):
    changed = False
    for item in state['accounts']:
        if item['status'] == 'running':
            item.update(status='unknown', message='上次执行中断，结果待确认；为避免重复签到不自动重试，请查看龙湖记录。')
            changed = True
    return changed


def run(context, store=None, now=None):
    accounts = load_accounts()
    store = store or ObsStore(context)
    now = (now or datetime.now(CST)).astimezone(CST)
    day = now.date().isoformat()
    slot = now.hour * 2 + now.minute // 30
    # Previous-day delivery retries and missed-account reporting survive midnight.
    previous = (now.date() - timedelta(days=1)).isoformat()
    old = store.load(previous)
    if old:
        changed = close_unfinished(old)
        for item in old['accounts']:
            if item['status'] == 'pending':
                item.update(status='missed', message='当天未获得执行机会，请检查触发器和运行日志。')
                changed = True
        if changed:
            store.save(previous, old)
        notify_pending(store, old)
    state = store.load(day)
    if state is None:
        state = make_plan(day, accounts)
        store.save(day, state)
    if state.get('version') == 1 and state.get('day') == day:
        legacy_hash = hashlib.sha256(json.dumps([a[0] for a in accounts]).encode()).hexdigest()
        if state.get('fingerprint') != legacy_hash:
            raise ValueError('旧计划账号配置不匹配，请恢复更新代码前的 token 数组后再迁移')
        # Preserve slots, completed results and notification markers; never rerun.
        state.update(version=2, fingerprint=make_plan(day, accounts)['fingerprint'])
        for item in state['accounts']:
            item['account_id'] = account_ids()[item['index']]
        store.save(day, state)
    if state.get('version') != 2 or state.get('day') != day:
        raise ValueError('OBS 当天计划格式不兼容，请检查存储记录')
    if state['fingerprint'] != make_plan(day, accounts)['fingerprint']:
        raise ValueError('当天账号标识或顺序已变更，请恢复原账号标识；避免签到串号')
    if close_unfinished(state):
        store.save(day, state)
    notify_pending(store, state)
    due = sorted((a for a in state['accounts'] if a['status'] == 'pending' and a['slot'] <= slot),
                 key=lambda a: a['slot'])
    if not due or state.get('last_execution_slot') == slot:
        return {'success': True, 'status': 'idle', 'day': day, 'message': '没有到期账号', 'progress': progress(state)}
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if (midnight - now).total_seconds() <= 900:
        return {'success': True, 'status': 'idle', 'day': day,
                'message': '距午夜不足完整执行时间，不启动新的签到', 'progress': progress(state)}
    # Catch up one account at each trigger, preserving separation after missed ticks.
    item = due[0]
    state['last_execution_slot'] = slot
    item.update(status='running', started_at=now.isoformat())
    store.save(day, state)  # Fail closed: no sign request until intent is durable.
    time.sleep(item['jitter'])
    try:
        outcome = execute_account(store, accounts, item['index'])
        status, message = outcome['status'], outcome['message']
        item['details'] = outcome
    except Exception as exc:
        status, message = 'unknown', '签到请求异常（{}），请确认龙湖签到记录。'.format(type(exc).__name__)
    item.update(status=status, message=redact(message, accounts), finished_at=datetime.now(CST).isoformat())
    store.save(day, state)
    notify_pending(store, state)
    return {'success': status == 'success', 'status': status, 'day': day,
            'account': item['name'], 'message': item['message'], 'progress': progress(state)}
