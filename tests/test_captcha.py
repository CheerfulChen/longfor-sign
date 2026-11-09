from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from core import captcha, client


@pytest.mark.parametrize('is_app',[False,True])
@pytest.mark.parametrize('returned_token',['verified-token','verified-token:server-challenge'])
def test_verification_uses_same_challenge_and_client_ua(is_app,returned_token):
    calls=[]; directories=[]
    session=Mock(); session.headers={}
    def response(data):
        result=Mock();result.json.return_value=data;return result
    session.get.side_effect=[response({'code':'200','data':'c'}),response({'success':True,'result':1,'sid':'test-sid','p1':'/api/p1','p2':'/api/p2'})]
    def post(url,**kwargs):
        calls.append(kwargs);return response({'success':True,'token':returned_token})
    session.post.side_effect=post
    def images(current,data,directory):
        assert current is session
        directories.append(directory);(Path(directory)/'temporary-image').write_bytes(b'test')
        return {'ac':'test-trajectory','x':12,'y':3}
    with patch.object(captcha.requests,'Session') as factory,patch.object(captcha,'image_payload',side_effect=images):
        factory.return_value.__enter__.return_value=session
        result=captcha.solve('custom-app-ua' if is_app else 'custom-mini-ua',is_app)
    init=session.get.call_args_list[1].kwargs['params']
    payload=calls[0]['data']
    assert payload['c']==init['c'] and payload['aid']==init['aid']
    assert payload['sid']=='test-sid' and payload['ac']=='test-trajectory'
    assert result==returned_token
    assert session.headers['User-Agent']==('custom-app-ua' if is_app else 'custom-mini-ua')
    assert 'token' not in session.headers and 'X-LF-UserToken' not in session.headers
    assert session.trust_env is False
    assert not Path(directories[0]).exists()


def test_failed_or_unsupported_verification_does_not_return_credentials():
    session=Mock();session.headers={}
    response=Mock();response.json.return_value={'code':'200','data':'other'}
    session.get.return_value=response
    with patch.object(captcha.requests,'Session') as factory,patch.object(captcha,'image_payload') as images:
        factory.return_value.__enter__.return_value=session
        assert captcha.solve('ua',True) is None
    images.assert_not_called();session.post.assert_not_called()


@pytest.mark.parametrize('url',['http://ly-ver.longhu.net/api/p1','https://evil.example/api/p1','//evil.example/api/p1','https://ly-ver.longhu.net@evil.example/api/p1','/other'])
def test_verification_image_hosts_are_restricted(url):
    with pytest.raises(ValueError):captcha._image_url(url)


@pytest.mark.parametrize('activity',[client.MINI_ACTIVITY,client.APP_ACTIVITY])
def test_risk_verifies_and_replays_once_with_same_profile(activity):
    with patch.object(client,'sign_state',side_effect=[False,False,False,True]) as calendar,patch.object(client,'solve_captcha',return_value='verified:challenge') as solve,patch.object(client,'_request',side_effect=[{'code':'8040012'},{'code':'0000'}]) as request:
        result=client.checkin('login','risk',activity,user_agent='captured-ua')
    assert result['status']=='success' and request.call_count==2
    solve.assert_called_once_with('captured-ua',activity==client.APP_ACTIVITY)
    initial,retry=[call.args[1] for call in request.call_args_list]
    assert 'X-LF-DXRisk-Captcha-Token' not in initial
    assert retry['X-LF-DXRisk-Captcha-Token']=='verified:challenge'
    assert initial['User-Agent']==retry['User-Agent']=='captured-ua'
    assert initial['token']==retry['token']=='login'
    assert initial['X-LF-DXRisk-Source']==retry['X-LF-DXRisk-Source']==('2' if activity==client.APP_ACTIVITY else '5')
    assert all(call.kwargs['user_agent']=='captured-ua' for call in calendar.call_args_list)


def test_failed_verification_is_bounded():
    with patch.object(client,'sign_state',side_effect=[False,False]),patch.object(client,'solve_captcha',return_value=None) as solve,patch.object(client,'_request',return_value={'code':'8040012'}) as request:
        result=client.checkin('login','risk',client.APP_ACTIVITY)
    assert result['status']=='risk' and '自动验证' in result['message']
    assert solve.call_count==request.call_count==1


@pytest.mark.parametrize('state,expected',[(True,'success'),(None,'unknown')])
def test_verification_does_not_replay_when_calendar_changed(state,expected):
    with patch.object(client,'sign_state',side_effect=[False,False,state]),patch.object(client,'solve_captcha',return_value='verified'),patch.object(client,'_request',return_value={'code':'8040012'}) as request:
        assert client.checkin('login','risk',client.APP_ACTIVITY)['status']==expected
    assert request.call_count==1


def test_uncertain_first_request_does_not_trigger_verification():
    with patch.object(client,'sign_state',side_effect=[False,None]),patch.object(client,'solve_captcha') as solve,patch.object(client,'_request',return_value={'code':'8040012'}):
        assert client.checkin('login','risk',client.APP_ACTIVITY)['status']=='unknown'
    solve.assert_not_called()


def test_original_trajectory_and_encoder_are_packaged_together():
    from core.captcha_support.trajectory_enhanced import generate_realistic_trajectory
    from core.captcha_support.ac_encoder_full import generate_ac
    trajectory=generate_realistic_trajectory(100)
    result=generate_ac(trajectory,trajectory[-1][0],trajectory[-1][1],sid='synthetic-session')
    assert isinstance(result,str) and result.startswith('s_v3#')


@pytest.mark.parametrize('width,height,raw_x,raw_y,server_y,expected_x,expected_y',[
    (400,200,296,91,68,197,68),
    (400,200,296,91,None,197,68),
    (300,150,222,68,68,197,68),
    (800,400,592,182,0,197,0),
    (400,200,253,61,45,164,45),
])
def test_image_coordinates_are_scaled_before_trajectory_and_ac(
        tmp_path,caplog,width,height,raw_x,raw_y,server_y,expected_x,expected_y):
    from PIL import Image
    from core.captcha_support import image_recognition_v2 as recognition
    from core.captcha_support import trajectory_enhanced as trajectories
    from core.captcha_support import ac_encoder_full as encoder
    def download(session,path,target):
        Image.new('RGB',(width,height) if path=='background' else (67,67)).save(target)
    data={'p1':'background','p2':'slider','sid':'private-session'}
    if server_y is not None:data['y']=server_y
    trajectory=[(0,0,0),(expected_x,0,1000)]
    with patch.object(captcha,'download',side_effect=download), \
         patch.object(recognition,'find_gap_position',return_value=(raw_x,raw_y)) as recognize, \
         patch.object(trajectories,'generate_realistic_trajectory',return_value=trajectory) as generate, \
         patch.object(encoder,'generate_ac',return_value='private-ac') as ac:
        payload=captcha.image_payload(Mock(),data,tmp_path)
    assert recognize.call_args.kwargs['apply_legacy_offset'] is False
    generate.assert_called_once_with(expected_x)
    ac.assert_called_once_with(trajectory,expected_x,expected_y,sid='private-session')
    assert payload=={'ac':'private-ac','x':expected_x,'y':expected_y}
    assert '验证码坐标换算' in caplog.text
    assert 'private-session' not in caplog.text and 'private-ac' not in caplog.text


def test_raw_image_matching_can_skip_legacy_offset():
    import numpy as np
    from core.captcha_support import image_recognition_v2 as recognition
    with patch.object(recognition.cv2,'imread',side_effect=lambda *args:np.zeros((200,400,3),dtype=np.uint8)), \
         patch.object(recognition,'detect_by_contour',return_value=(296,91,0.5)), \
         patch.object(recognition,'detect_by_color_diff',return_value=(296,91,0.5)), \
         patch.object(recognition,'detect_by_shape_match',return_value=(296,91,0.5)):
        assert recognition.find_gap_position('bg','slider',apply_legacy_offset=False)==(296,91)
        assert recognition.find_gap_position('bg','slider')==(205,91)
