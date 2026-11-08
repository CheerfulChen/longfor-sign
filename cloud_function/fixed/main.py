"""Legacy fixed TIMER entry: one invocation handles all configured accounts."""
import os
from core.file_store import FileStore
from core.obs_store import ObsStore
from bark_notify import notify_sign_result
from longfor import longfor_sign


def main(event, context):
    try:
        store = ObsStore(context) if os.environ.get('SIGN_OBS_BUCKET','').strip() else FileStore(os.environ.get('SIGN_STATE_DIR','/tmp/longfor-sign-fixed'))
        result = longfor_sign(store=store,start_delay=(0,300))
        success, message = result[:2]
        count, total = result[2:] if len(result) == 4 else (None, None)
        notified = notify_sign_result(message.split('\n'), success, count, total)
        return {'success': success, 'status': 'success' if success else 'failed',
                'message': message, 'success_count': count, 'total_count': total,
                'notified': bool(notified)}
    except Exception as exc:
        # Never serialize request exception text or credential configuration.
        return {'success': False, 'status': 'error',
                'message': '固定触发签到异常：'+type(exc).__name__}
