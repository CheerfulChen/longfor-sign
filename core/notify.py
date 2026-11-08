"""Bark transport shared by script and FunctionGraph entrypoints."""
import os
import time
import requests


def send_bark_notification(title, content, group='龙湖天街签到'):
    key=os.environ.get('BARK_KEY','').strip()
    server=(os.environ.get('BARK_SERVER') or 'https://api.day.app').rstrip('/')
    if not key or not server.startswith('https://'):return False
    payload=dict(device_key=key,title=title,body=content,group=group,isArchive='1')
    for attempt in range(2):
        try:
            with requests.Session() as session:
                session.trust_env=False
                response=session.post(server+'/push',json=payload,timeout=(5,10),allow_redirects=False)
            if response.status_code==200 and response.json().get('code')==200:return True
        except (requests.RequestException,ValueError):pass
        if attempt==0:time.sleep(1)
    return False


def notify_sign_result(results,success,success_count=None,total_count=None):
    title='✅ 龙湖签到成功' if success else '⚠️ 龙湖签到未全部成功'
    if success_count is not None:title+=' ({}/{})'.format(success_count,total_count)
    return send_bark_notification(title,'\n'.join(results))
