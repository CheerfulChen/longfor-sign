"""Fixed-trigger batch execution shared by CLI, Actions and FunctionGraph."""
import os
import random
import time
from .accounts import load_accounts
from .file_store import FileStore
from .service import execute_persisted


def _bounds(prefix,low,high):
    try:
        values=(int(os.environ.get(prefix+'_MIN_SECONDS',low)),int(os.environ.get(prefix+'_MAX_SECONDS',high)))
    except ValueError:raise ValueError('等待时间必须是整数') from None
    if not 0<=values[0]<=values[1]<=600:raise ValueError('等待范围需满足 0 <= 最小值 <= 最大值 <= 600 秒')
    return values


def run(store=None, start_delay=(0,0)):
    accounts=load_accounts()
    start=_bounds('SIGN_START_DELAY',*start_delay)
    gap=_bounds('SIGN_ACCOUNT_INTERVAL',20,60)
    if len(accounts)>1 and gap[0]<1:raise ValueError('多账号间隔至少为 1 秒')
    store=store or FileStore(os.environ.get('SIGN_STATE_DIR','.state'))
    random.SystemRandom().shuffle(accounts)
    time.sleep(random.SystemRandom().randint(*start))
    results=[];good=0
    for position,account in enumerate(accounts):
        if position:time.sleep(random.SystemRandom().randint(*gap))
        try:
            result=execute_persisted(store,account)
        except Exception as exc:
            result={'status':'unknown','message':'执行异常（{}），请检查配置及客户端记录'.format(type(exc).__name__)}
        good+=result['status']=='success'
        results.append(account['name']+'：'+result['message'])
    return good==len(accounts),'\n'.join(results),good,len(accounts)
