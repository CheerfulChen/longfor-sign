import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet

DEFAULTS = {'mode': 'all_day', 'start': '08:00', 'end': '22:00',
            'timezone': 'Asia/Shanghai', 'gap_minutes': 15, 'enabled': True}
CREDENTIALS = ('token', 'risk', 'app_risk', 'app_token', 'app_captcha', 'mini_user_agent', 'app_user_agent')
TERMINAL = ('success', 'partial', 'failed', 'risk', 'unknown', 'missed')


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'longfor.db'
        key_path = self.directory / '.key'
        if not key_path.exists() and self.path.exists():
            raise RuntimeError('数据库已存在但缺少加密密钥，请从同一份备份恢复 .key')
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as output:
                output.write(Fernet.generate_key())
                output.flush()
                os.fsync(output.fileno())
        self.key = key_path.read_bytes()
        self.cipher = Fernet(self.key)
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS accounts (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, token TEXT NOT NULL,
                  risk TEXT NOT NULL, app_risk TEXT NOT NULL, enabled INTEGER NOT NULL,
                  app_enabled INTEGER NOT NULL, updated REAL NOT NULL, refreshed REAL);
                CREATE TABLE IF NOT EXISTS plans (day TEXT PRIMARY KEY, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, day TEXT NOT NULL, account_id TEXT NOT NULL,
                  name TEXT NOT NULL, run_at REAL NOT NULL, window_end REAL NOT NULL,
                  state TEXT NOT NULL DEFAULT 'pending', message TEXT NOT NULL DEFAULT '',
                  details TEXT NOT NULL DEFAULT '{}', manual INTEGER NOT NULL DEFAULT 0,
                  started REAL, finished REAL, notified INTEGER NOT NULL DEFAULT 0,
                  notify_attempts INTEGER NOT NULL DEFAULT 0, notify_after REAL NOT NULL DEFAULT 0,
                  UNIQUE(day, account_id));
                CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state, run_at);
                CREATE TABLE IF NOT EXISTS summaries (
                  day TEXT PRIMARY KEY, sent INTEGER NOT NULL DEFAULT 0,
                  attempts INTEGER NOT NULL DEFAULT 0, retry_after REAL NOT NULL DEFAULT 0);
            ''')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(accounts)')}
            for column in ('app_token', 'app_captcha', 'mini_user_agent', 'app_user_agent'):
                if column not in columns:
                    db.execute(f"ALTER TABLE accounts ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('settings', json.dumps(DEFAULTS)))
        os.chmod(self.path, 0o600)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=20000')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def encrypt(self, text):
        return self.cipher.encrypt(text.encode()).decode()

    def decrypt(self, text):
        return self.cipher.decrypt(text.encode()).decode() if text else ''

    def settings(self, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.settings(conn)
        return json.loads(db.execute("SELECT value FROM meta WHERE key='settings'").fetchone()[0])

    def list_accounts(self, db=None, private=False):
        if db is None:
            with self.transaction() as conn:
                return self.list_accounts(conn, private)
        rows = [dict(r) for r in db.execute('SELECT * FROM accounts ORDER BY updated,id')]
        for row in rows:
            for key in CREDENTIALS:
                value = self.decrypt(row.pop(key))
                row['has_' + key] = bool(value)
                if private:
                    row[key] = value
            row['enabled'] = bool(row['enabled'])
            row['app_enabled'] = bool(row['app_enabled'])
        return rows

    def save_account(self, payload, ident=None, planner=None):
        if not isinstance(payload, dict):
            raise ValueError('账号配置必须是 JSON 对象')
        with self.transaction() as db:
            rows = self.list_accounts(db, private=True)
            if ident and db.execute("SELECT 1 FROM jobs WHERE account_id=? AND state='running'", (ident,)).fetchone():
                raise ValueError('账号正在执行，请结束后再修改')
            original = next((a for a in rows if a['id'] == ident), None)
            if ident and not original:
                raise ValueError('账号不存在')
            if not ident and len(rows) >= 50:
                raise ValueError('最多配置 50 个账号')
            name = payload.get('name', original['name'] if original else '')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
                raise ValueError('账号名称需为 1～40 个字符')
            fields = {}
            for key in CREDENTIALS:
                value = payload.get(key, '')
                if not isinstance(value, str) or len(value) > 4096:
                    raise ValueError('凭据格式不正确')
                fields[key] = value.strip() or (original[key] if original else '')
            if payload.get('clear_app_captcha') is True:
                fields['app_captcha'] = ''
            if fields['app_captcha'].lower() == 'undefined':
                raise ValueError('undefined 不是有效的验证码凭据，请留空')
            if any('\r' in v or '\n' in v for v in fields.values()):
                raise ValueError('凭据中不能包含换行，请直接复制原始请求头值')
            for key in ('mini_user_agent', 'app_user_agent'):
                if len(fields[key]) > 1024 or any(ord(c)<32 or ord(c)>126 for c in fields[key]):
                    raise ValueError('User-Agent 需为不含换行的 ASCII 文本，最多 1024 字符')
            flags = {}
            for key, default in (('enabled', True), ('app_enabled', False)):
                value = payload.get(key, original[key] if original else default)
                if not isinstance(value, bool):
                    raise ValueError('账号开关必须是布尔值')
                flags[key] = value
            if not fields['token'] or not fields['risk']:
                raise ValueError('请填写登录 token 和小程序风控 token')
            if flags['app_enabled'] and (not fields['app_risk'] or not fields['app_token']):
                raise ValueError('开启 APP 前请填写该账号独立的 APP 登录 token 和风控 token')
            for row in rows:
                if row['id'] == ident:
                    continue
                if set(filter(None, (row['token'], row['app_token']))) & set(filter(None, (fields['token'], fields['app_token']))):
                    raise ValueError('此登录凭据已被其他账号使用')
                if set(filter(None, (row['risk'], row['app_risk']))) & set(filter(None, (fields['risk'], fields['app_risk']))):
                    raise ValueError('不同账号不能共用风控 token')
            ident = ident or uuid.uuid4().hex
            db.execute('''INSERT INTO accounts(id,name,token,risk,app_risk,app_token,app_captcha,mini_user_agent,app_user_agent,enabled,app_enabled,updated)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,token=excluded.token,risk=excluded.risk,app_risk=excluded.app_risk,
                app_token=excluded.app_token,app_captcha=excluded.app_captcha,mini_user_agent=excluded.mini_user_agent,app_user_agent=excluded.app_user_agent,enabled=excluded.enabled,app_enabled=excluded.app_enabled,updated=excluded.updated''',
                (ident, name.strip(), self.encrypt(fields['token']), self.encrypt(fields['risk']),
                 self.encrypt(fields['app_risk']), self.encrypt(fields['app_token']),
                 self.encrypt(fields['app_captcha']), self.encrypt(fields['mini_user_agent']),
                 self.encrypt(fields['app_user_agent']), flags['enabled'], flags['app_enabled'], time.time()))
            if planner:
                planner(db)
        return ident

    def update_token(self, ident, token):
        with self.transaction() as db:
            db.execute('UPDATE accounts SET token=?,refreshed=? WHERE id=?',
                       (self.encrypt(token), time.time(), ident))

    def public_settings(self):
        settings = self.settings()
        settings.pop('bark_key', None)
        settings['has_bark_key'] = bool(self.settings().get('bark_key'))
        return settings

    def rows(self, sql, params=()):
        with self.transaction() as db:
            return [dict(r) for r in db.execute(sql, params)]
