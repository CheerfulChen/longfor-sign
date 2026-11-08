import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .scheduling import dates, ensure_plans, validate
from .storage import Store
from .worker import Worker


def create_app(config=None):
    config = config or {}
    password = config.get('ADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD', '')
    username = config.get('ADMIN_USERNAME') or os.environ.get('ADMIN_USERNAME', 'admin')
    if len(password) < 12 or password.startswith('CHANGE_ME'):
        raise RuntimeError('请设置至少 12 位的 ADMIN_PASSWORD，不能使用样例占位值')
    store = Store(config.get('DATA_DIR') or os.environ.get('DATA_DIR', '/data'))
    app = Flask(__name__)
    app.config.update(SECRET_KEY=hashlib.sha256(store.key + password.encode()).hexdigest(),
                      MAX_CONTENT_LENGTH=64 * 1024, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict', PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                      SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'false').lower() == 'true')
    password_hash = generate_password_hash(password)
    failures, rate_lock = {}, threading.Lock()
    worker = Worker(store)
    app.extensions.update(store=store, sign_worker=worker)

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']

    @app.before_request
    def protect():
        if request.path == '/healthz' or request.path.startswith('/static/'):
            return None
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            supplied = request.headers.get('X-CSRF-Token', '')
            expected = session.get('csrf', '')
            if not expected or not hmac.compare_digest(supplied, expected):
                return jsonify(error='会话校验失败，请刷新页面'), 403
        if request.path in ('/', '/api/login'):
            return None
        if not session.get('authenticated') or time.time() - session.get('issued', 0) > 28800:
            return jsonify(error='请先登录'), 401
        return None

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.errorhandler(ValueError)
    def bad_value(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(413)
    def too_large(exc):
        return jsonify(error='请求内容过大'), 413

    @app.errorhandler(500)
    def server_error(exc):
        return jsonify(error='服务异常，请检查容器运行日志和数据目录'), 500

    @app.get('/healthz')
    def health():
        return jsonify(status='ok')

    @app.get('/')
    def index():
        authenticated = session.get('authenticated') and time.time() - session.get('issued', 0) <= 28800
        return render_template('index.html' if authenticated else 'login.html', csrf=csrf())

    @app.post('/api/login')
    def login():
        ip = request.remote_addr or 'unknown'
        now = time.time()
        with rate_lock:
            count, until = failures.get(ip, (0, 0))
            if count >= 5 and until > now:
                return jsonify(error='登录尝试过多，请 10 分钟后再试'), 429
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(error='登录参数格式不正确'), 400
        supplied_user = data.get('username', '')
        supplied_password = data.get('password', '')
        if not isinstance(supplied_password, str) or not isinstance(supplied_user, str):
            return jsonify(error='用户名或密码错误'), 401
        valid_password = check_password_hash(password_hash, supplied_password)
        if supplied_user != username or not valid_password:
            with rate_lock:
                if len(failures) > 1000:
                    failures.clear()
                failures[ip] = ((count if until > now else 0) + 1, now + 600)
            return jsonify(error='用户名或密码错误'), 401
        with rate_lock:
            failures.pop(ip, None)
        session.clear()
        session.update(authenticated=True, issued=now, csrf=secrets.token_urlsafe(32))
        session.permanent = True
        return jsonify(ok=True)

    @app.post('/api/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/dashboard')
    def dashboard():
        now = time.time()
        settings = store.public_settings()
        today, tomorrow = dates(now, settings)
        accounts = store.list_accounts()
        jobs = store.rows('SELECT * FROM jobs WHERE day=? ORDER BY run_at', (today,))
        history = store.rows("SELECT * FROM jobs WHERE state NOT IN ('pending','cancelled') ORDER BY COALESCE(started,run_at) DESC LIMIT 100")
        upcoming = store.rows("SELECT * FROM jobs WHERE state='pending' AND window_end>? ORDER BY run_at LIMIT 100", (now,))
        def present(items):
            for job in items:
                job['details'] = json.loads(job['details'])
            return items
        return jsonify(settings=settings, accounts=accounts, today=today, now=now,
                       jobs=present(jobs), history=present(history), upcoming=present(upcoming))

    @app.post('/api/accounts')
    def add_account():
        data = request.get_json(silent=True)
        ident = store.save_account(data, planner=lambda db: ensure_plans(store, db, replace=True))
        return jsonify(id=ident), 201

    @app.put('/api/accounts/<ident>')
    def edit_account(ident):
        data = request.get_json(silent=True)
        if store.rows("SELECT id FROM jobs WHERE account_id=? AND state='running'", (ident,)):
            raise ValueError('该账号正在执行，请结束后再修改')
        store.save_account(data, ident, planner=lambda db: ensure_plans(store, db, replace=True))
        return jsonify(ok=True)

    @app.delete('/api/accounts/<ident>')
    def delete_account(ident):
        with store.transaction() as db:
            if db.execute("SELECT id FROM jobs WHERE account_id=? AND state='running'", (ident,)).fetchone():
                raise ValueError('该账号正在执行，请结束后再删除')
            db.execute('DELETE FROM accounts WHERE id=?', (ident,))
            db.execute("UPDATE jobs SET state='cancelled' WHERE account_id=? AND state='pending'", (ident,))
            ensure_plans(store, db, replace=True)
        return jsonify(ok=True)

    @app.post('/api/accounts/<ident>/run')
    def manual(ident):
        now = time.time()
        with store.transaction() as db:
            account = db.execute('SELECT * FROM accounts WHERE id=? AND enabled=1', (ident,)).fetchone()
            if not account:
                raise ValueError('账号不存在或已停用')
            settings = store.settings(db)
            day = dates(now, settings)[0]
            old = db.execute('SELECT * FROM jobs WHERE day=? AND account_id=?', (day, ident)).fetchone()
            if old and old['state'] not in ('pending', 'cancelled'):
                return jsonify(error='今天已有执行记录，不重复签到；请查看执行记录'), 409
            tz = ZoneInfo(settings['timezone'])
            midnight = (datetime.fromtimestamp(now, tz) + timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            db.execute('''INSERT INTO jobs(id,day,account_id,name,run_at,window_end,manual)
                VALUES(?,?,?,?,?,?,1) ON CONFLICT(day,account_id) DO UPDATE SET
                run_at=excluded.run_at,window_end=excluded.window_end,state='pending',manual=1''',
                (uuid.uuid4().hex, day, ident, account['name'], now, midnight))
        return jsonify(ok=True, message='已加入执行队列，将遵守账号间最小间隔')

    @app.put('/api/settings')
    def settings_update():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('设置格式不正确')
        with store.transaction() as db:
            settings = store.settings(db)
            original_schedule = {k: settings[k] for k in ('mode','start','end','timezone','gap_minutes','enabled')}
            for key in ('mode','start','end','timezone','gap_minutes','enabled'):
                if key in data:
                    settings[key] = data[key]
            if 'bark_key' in data and data['bark_key']:
                if not isinstance(data['bark_key'], str) or len(data['bark_key']) > 512:
                    raise ValueError('Bark Key 格式不正确')
                settings['bark_key'] = store.encrypt(data['bark_key'].strip())
            if data.get('clear_bark_key') is True:
                settings.pop('bark_key', None)
            count = db.execute('SELECT COUNT(*) FROM accounts WHERE enabled=1').fetchone()[0]
            validate(settings, count)
            db.execute("UPDATE meta SET value=? WHERE key='settings'", (json.dumps(settings),))
            if any(settings[k] != v for k, v in original_schedule.items()):
                ensure_plans(store, db, replace=True)
        return jsonify(ok=True)

    @app.post('/api/notifications/test')
    def test_notification():
        ok = worker.send('Longfor Sign · 测试推送', '推送已连接，之后会在这里收到签到结果。')
        return jsonify(ok=ok, message='测试推送已发送' if ok else '推送失败，请检查 Bark Key 和服务器网络'), (200 if ok else 400)

    if config.get('START_WORKER', True):
        worker.start()
    return app
