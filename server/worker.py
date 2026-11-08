import fcntl
import json
import logging
import threading
import time
from datetime import datetime

import requests
from core import client
from .scheduling import ensure_plans


class Worker:
    def __init__(self, store):
        self.store = store
        self.stop_event = threading.Event()
        self.lock_file = None

    def start(self):
        self.lock_file = open(self.store.directory / '.worker.lock', 'a')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            raise RuntimeError('数据目录已被另一个服务使用，请保持单实例、单 worker') from None
        now = time.time()
        with self.store.transaction() as db:
            running = db.execute("SELECT COUNT(*) FROM jobs WHERE state='running'").fetchone()[0]
            db.execute("UPDATE jobs SET state='unknown',message=?,finished=? WHERE state='running'",
                       ('上次执行中断，结果待确认；请在客户端核实，不自动重试。', now))
            if running:
                db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('last_finish', str(now)))
        self.thread = threading.Thread(target=self.loop, name='sign-scheduler', daemon=True)
        self.thread.start()

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                logging.error('调度异常：%s', type(exc).__name__)
            self.stop_event.wait(5)

    def claim(self, now):
        with self.store.transaction() as db:
            ensure_plans(self.store, db, now)
            db.execute("UPDATE jobs SET state='missed',message=?,finished=? WHERE state='pending' AND window_end<=?",
                       ('时间段已结束，未执行；请检查服务运行时间或调整间隔。', now, now))
            if db.execute("SELECT 1 FROM jobs WHERE state='running' LIMIT 1").fetchone():
                return None
            settings = self.store.settings(db)
            last = db.execute("SELECT value FROM meta WHERE key='last_finish'").fetchone()
            if last and now < float(last[0]) + settings['gap_minutes'] * 60:
                return None
            job = db.execute('''SELECT j.* FROM jobs j JOIN accounts a ON j.account_id=a.id
                WHERE j.state='pending' AND a.enabled=1 AND j.run_at<=? AND j.window_end>?
                AND (?=1 OR j.manual=1) ORDER BY j.run_at,j.id LIMIT 1''',
                (now, now, int(settings['enabled']))).fetchone()
            if job is None:
                return None
            db.execute("UPDATE jobs SET state='running',started=? WHERE id=? AND state='pending'", (now, job['id']))
            account = next(a for a in self.store.list_accounts(db, private=True) if a['id'] == job['account_id'])
            # Captcha credentials are supplied by the user for one task only.
            if account['app_captcha']:
                db.execute("UPDATE accounts SET app_captcha='' WHERE id=?", (account['id'],))
            return dict(job), account

    def execute(self, account):
        from core.service import execute
        result = execute(account, save_token=lambda token:self.store.update_token(account['id'],token),
                         wait=self.stop_event.wait, stopped=self.stop_event.is_set)
        details={key:result[key] for key in ('refresh','mini','app')}
        return result['status'],result['message'],details

    def tick(self, now=None):
        now = time.time() if now is None else now
        claimed = self.claim(now)
        if claimed:
            job, account = claimed
            try:
                state, message, details = self.execute(account)
            except Exception as exc:
                state, message, details = 'unknown', '执行异常（{}），请核实客户端记录；不自动重试。'.format(type(exc).__name__), {}
            finished = time.time()
            with self.store.transaction() as db:
                db.execute('UPDATE jobs SET state=?,message=?,details=?,finished=? WHERE id=?',
                           (state, message, json.dumps(details, ensure_ascii=False), finished, job['id']))
                db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('last_finish', str(finished)))
        self.deliver(now)
        return bool(claimed)

    def send(self, title, body):
        settings = self.store.settings()
        key = self.store.decrypt(settings.get('bark_key', ''))
        if not key:
            return False
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.post('https://api.day.app/push', json={
                    'device_key': key, 'title': title, 'body': body, 'group': '龙湖签到', 'isArchive': '1'},
                    timeout=(5, 10), allow_redirects=False)
            return response.status_code == 200 and response.json().get('code') == 200
        except (requests.RequestException, ValueError):
            return False

    def deliver(self, now):
        rows = self.store.rows("""SELECT * FROM jobs WHERE state IN
            ('success','partial','failed','risk','unknown','missed') AND notified=0 AND notify_after<=?
            ORDER BY finished LIMIT 20""", (now,))
        for job in rows:
            ok = self.send('龙湖签到 · {} · {}'.format(job['name'], job['state']),
                           '{}\n{}'.format(job['day'], job['message']))
            delay = min(21600, 300 * (2 ** min(job['notify_attempts'], 6)))
            with self.store.transaction() as db:
                db.execute('UPDATE jobs SET notified=?,notify_attempts=notify_attempts+1,notify_after=? WHERE id=?',
                           (int(ok), now + delay, job['id']))
        days = self.store.rows("SELECT DISTINCT day FROM jobs WHERE state NOT IN ('pending','running','cancelled')")
        for item in days:
            day = item['day']
            jobs = self.store.rows("SELECT * FROM jobs WHERE day=? AND state!='cancelled' ORDER BY run_at", (day,))
            if not jobs or any(j['state'] in ('pending', 'running') for j in jobs):
                continue
            with self.store.transaction() as db:
                db.execute('INSERT OR IGNORE INTO summaries(day) VALUES(?)', (day,))
                summary = dict(db.execute('SELECT * FROM summaries WHERE day=?', (day,)).fetchone())
            if summary['sent'] or summary['retry_after'] > now:
                continue
            body = '\n'.join('{}：{}\n{}'.format(j['name'], j['state'], j['message']) for j in jobs)
            ok = self.send('龙湖 {} 每日汇总'.format(day), body[:10000])
            delay = min(21600, 300 * (2 ** min(summary['attempts'], 6)))
            with self.store.transaction() as db:
                db.execute('UPDATE summaries SET sent=?,attempts=attempts+1,retry_after=? WHERE day=?',
                           (int(ok), now + delay, day))
