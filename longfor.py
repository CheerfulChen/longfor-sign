"""Compatibility entry; all active deployments use the common core."""
from core.accounts import load_tokens_json as _load_tokens_json
from core.batch import run
from core import client


def longfor_sign_single(token, dxrisk_token, max_retry=2):
    result=client.checkin(token,dxrisk_token,client.MINI_ACTIVITY,auto_captcha=max_retry>0)
    return result['status']=='success',result['message']


def longfor_sign(store=None, start_delay=(0,0)):
    try:return run(store=store,start_delay=start_delay)
    except ValueError as exc:return False,str(exc),0,0


if __name__=='__main__':
    print(longfor_sign()[1])
