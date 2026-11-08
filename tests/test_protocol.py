from datetime import datetime
from unittest.mock import Mock, patch

from core import client


def test_refresh_requires_valid_initial_session():
    with patch.object(client,'_request',return_value={'code':'801007','message':'secret-token'}) as request:
        token,message=client.refresh_token('old')
    assert token is None and 'secret-token' not in message
    assert request.call_count==1


def test_refresh_chain_and_no_fake_expiry():
    with patch.object(client,'_request',side_effect=[{'data':{'key':'key'}},{'code':'0000','data':{'token':'new'}}]) as request:
        assert client.refresh_token('old')[0]=='new'
    assert request.call_args_list[0][0][1]['lmToken']=='old'
    assert request.call_args_list[1][0][2]['key']=='key'


def test_calendar_before_clock_prevents_duplicate():
    with patch.object(client,'sign_state',return_value=True),patch.object(client,'_request') as request:
        assert client.checkin('t','r',client.MINI_ACTIVITY)['status']=='success'
    request.assert_not_called()


def test_unavailable_calendar_is_not_assumed_unsigned():
    with patch.object(client,'sign_state',return_value=None),patch.object(client,'_request') as request:
        assert client.checkin('t','r',client.MINI_ACTIVITY)['status']=='failed'
    request.assert_not_called()


def test_false_positive_clock_not_reported_as_success():
    with patch.object(client,'sign_state',side_effect=[False,False]),patch.object(client,'_request',return_value={'code':'0000'}):
        assert client.checkin('t','r',client.MINI_ACTIVITY)['status']=='failed'


def test_clock_error_but_calendar_success():
    with patch.object(client,'sign_state',side_effect=[False,True]),patch.object(client,'_request',return_value={'code':'8040012'}):
        assert client.checkin('t','r',client.MINI_ACTIVITY)['status']=='success'


def test_risk_is_distinct_and_no_automatic_captcha():
    with patch.object(client,'sign_state',side_effect=[False,False]),patch.object(client,'_request',return_value={'code':'8040012'}) as request:
        assert client.checkin('t','r',client.MINI_ACTIVITY,auto_captcha=False)['status']=='risk'
    assert request.call_count==1


def test_uncertain_after_clock_stays_unknown():
    with patch.object(client,'sign_state',side_effect=[False,None]),patch.object(client,'_request',return_value={'code':'0000'}):
        assert client.checkin('t','r',client.MINI_ACTIVITY)['status']=='unknown'


def test_calendar_uses_server_beijing_date():
    now=datetime(2026,11,7,0,10,tzinfo=client.CST)
    response={'code':'0000','data':{'current_date_time':str(int(now.timestamp()*1000)),
        'seven_days_signs':[{'sign_year':2026,'sign_month':11,'sign_day':7,'sign_status':20}]}}
    with patch.object(client,'_request',return_value=response):
        assert client.sign_state('t','r',client.MINI_ACTIVITY) is True


def test_outbound_proxy_and_redirect_controls():
    response=Mock(status_code=200,json=lambda:{'code':'0000'})
    session=Mock();session.post.return_value=response
    with patch.object(client.requests,'Session') as factory:
        factory.return_value.__enter__.return_value=session
        assert client._request('/test',{}, {})=={'code':'0000'}
    assert session.trust_env is False
    assert session.post.call_args.kwargs['allow_redirects'] is False


def test_app_and_mini_use_separate_client_profiles():
    mini=client.task_headers('mini-login','mini-risk',client.MINI_ACTIVITY)
    app=client.task_headers('app-login','app-risk',client.APP_ACTIVITY,'manual-captcha')
    assert (mini['X-LF-Bu-Code'],mini['X-LF-Channel'],mini['X-LF-DXRisk-Source'])==('C20400','C2','5')
    assert (app['X-LF-Bu-Code'],app['X-LF-Channel'],app['X-LF-DXRisk-Source'])==('L00602','L0','2')
    assert 'MicroMessenger' in mini['User-Agent'] and 'MAIAWebKit' in app['User-Agent']
    assert app['token']==app['X-LF-UserToken']=='app-login'
    assert app['X-LF-DXRisk-Captcha-Token']=='manual-captcha'
    assert 'X-LF-DXRisk-Captcha-Token' not in mini
    assert 'X-LF-DXRisk-Captcha-Token' not in client.task_headers('t','r',client.APP_ACTIVITY,'undefined')


def test_app_captcha_only_attached_to_clock():
    calendar={'code':'0000','data':{'seven_days_signs':[]}}
    with patch.object(client,'sign_state',side_effect=[False,True]),patch.object(client,'_request',return_value={'code':'0000'}) as request:
        assert client.checkin('app-login','app-risk',client.APP_ACTIVITY,captcha='manual-captcha')['status']=='success'
    assert request.call_args.args[1]['X-LF-DXRisk-Captcha-Token']=='manual-captcha'
    with patch.object(client,'_request',return_value=calendar) as request:
        client.sign_state('app-login','app-risk',client.APP_ACTIVITY)
    assert request.call_args.args[1]['X-LF-DXRisk-Source']=='2'
    assert 'X-LF-DXRisk-Captcha-Token' not in request.call_args.args[1]
