"""Persistent daily random plans. All timestamps are UTC Unix seconds."""
import json
import random
import re
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def minute(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00', value):
        raise ValueError('时间必须是 HH:MM 格式')
    hour, part = map(int, value.split(':'))
    return hour * 60 + part


def validate(settings, count):
    if settings.get('mode') not in ('all_day', 'window'):
        raise ValueError('请选择全天随机或时间段随机')
    try:
        ZoneInfo(settings['timezone'])
    except (ZoneInfoNotFoundError, KeyError, TypeError, ValueError):
        raise ValueError('时区无效，请使用 Asia/Shanghai 等 IANA 名称') from None
    if not isinstance(settings.get('enabled'), bool):
        raise ValueError('调度开关无效')
    gap = settings.get('gap_minutes')
    if isinstance(gap, bool) or not isinstance(gap, int) or not 1 <= gap <= 1440:
        raise ValueError('账号间隔需为 1～1440 分钟的整数')
    start, end = bounds_minutes(settings)
    if start >= end:
        raise ValueError('时间段结束必须晚于开始；当前版本请选择同一天内的时间段')
    if (end - start) * 60 - max(0, count - 1) * gap * 60 < max(1, count):
        raise ValueError('时间段太短，无法容纳所有账号和最小间隔；请扩大时间段或缩短间隔')


def bounds_minutes(settings):
    # Leave enough headroom for a running request before midnight.
    return (0, 1430) if settings['mode'] == 'all_day' else (minute(settings['start']), minute(settings['end']))


def dates(now, settings):
    today = datetime.fromtimestamp(now, ZoneInfo(settings['timezone'])).date()
    return [today.isoformat(), (today + timedelta(days=1)).isoformat()]


def bounds(day, settings):
    tz = ZoneInfo(settings['timezone'])
    base = datetime.fromisoformat(day).replace(tzinfo=tz)
    start, end = bounds_minutes(settings)
    return (base + timedelta(minutes=start)).timestamp(), (base + timedelta(minutes=end)).timestamp()


def random_times(start, end, count, gap, rng=None):
    if count == 0:
        return []
    low, high = int(start) + 1, int(end)
    available = high - low - (count - 1) * gap
    if available < count:
        raise ValueError('今天剩余时间不足以重新安排任务，请扩大时间段；也可在窗口结束后保存，明天开始执行')
    rng = rng or random.SystemRandom()
    points = sorted(rng.sample(range(available), count))
    return [low + point + i * gap for i, point in enumerate(points)]


def ensure_plans(store, db, now=None, replace=False):
    now = now if now is not None else time.time()
    settings = store.settings(db)
    accounts = [dict(r) for r in db.execute('SELECT id,name FROM accounts WHERE enabled=1 ORDER BY id')]
    validate(settings, len(accounts))
    days = dates(now, settings)
    if replace:
        # Cancel future old-timezone plans but retain all execution history.
        db.execute("UPDATE jobs SET state='cancelled' WHERE state='pending' AND day NOT IN (?,?)", days)
    for day in days:
        if not replace and db.execute('SELECT 1 FROM plans WHERE day=?', (day,)).fetchone():
            continue
        start, end = bounds(day, settings)
        existing = {r['account_id']: r for r in db.execute('SELECT * FROM jobs WHERE day=?', (day,))}
        eligible = [a for a in accounts if a['id'] not in existing or existing[a['id']]['state'] in ('pending', 'cancelled')]
        gap = settings['gap_minutes'] * 60
        fixed = [r for r in existing.values() if r['state'] not in ('pending', 'cancelled')]
        last = max([float(r['finished'] or r['started'] or r['run_at']) for r in fixed] + [0])
        # No new jobs before existing executions plus the configured interval.
        low = max(start, now, last + gap if fixed else start)
        times = random_times(low, end, len(eligible), gap) if low < end else []
        random.SystemRandom().shuffle(eligible)
        db.execute("UPDATE jobs SET state='cancelled' WHERE day=? AND state='pending'", (day,))
        for account, stamp in zip(eligible, times):
            old = existing.get(account['id'])
            db.execute('''INSERT INTO jobs(id,day,account_id,name,run_at,window_end,state)
                VALUES(?,?,?,?,?,?,'pending') ON CONFLICT(day,account_id) DO UPDATE SET
                name=excluded.name,run_at=excluded.run_at,window_end=excluded.window_end,
                state='pending',manual=0,message='',details='{}' ''',
                (old['id'] if old else uuid.uuid4().hex, day, account['id'], account['name'], stamp, end))
        db.execute('INSERT OR REPLACE INTO plans VALUES (?,?)', (day, now))
