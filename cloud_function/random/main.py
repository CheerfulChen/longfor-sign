from datetime import datetime

from bark_notify import send_bark_notification
from daily_scheduler import CST, run


def main(event, context):
    # Manual test also follows the durable plan; it never signs all accounts at once.
    try:
        result = run(context)
    except Exception as exc:
        # Avoid leaking credentials embedded in SDK or JSON exception strings.
        detail = str(exc) if type(exc) in (ValueError, RuntimeError) else type(exc).__name__
        message = '调度失败：{}。请检查账号配置、OBS 桶及函数委托。'.format(detail)
        print(message, flush=True)
        # Infrastructure failures cannot use durable notification markers.
        # Alert only on the hourly TIMER tick to limit noise during an outage.
        if datetime.now(CST).minute < 5:
            send_bark_notification('⚠️ 龙湖签到调度异常', message)
        return {'success': False, 'status': 'error', 'message': message}
    print(result, flush=True)
    return result
