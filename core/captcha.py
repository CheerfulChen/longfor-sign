"""Bounded adapter for the original image/trajectory verification routines.

Uses a per-attempt temporary directory; never logs verification credentials.
"""
import random
import os
import json
import shutil
import uuid
import secrets
import string
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

VERIFY_BASE = 'https://ly-ver.longhu.net'
APP_ID = 'd1a43734fc59aeae9f1562dbd70fdf54'
MAX_IMAGE = 2 * 1024 * 1024


def _json(response):
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise ValueError('Invalid verification response')
    return value


def _image_url(path):
    url = urljoin(VERIFY_BASE, path)
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != 'ly-ver.longhu.net' or not parts.path.startswith('/api/p'):
        raise ValueError('Invalid verification image URL')
    return url


def download(session, path, target):
    with session.get(_image_url(path), timeout=(5, 10), allow_redirects=False, stream=True) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Invalid image response')
        size = 0
        with target.open('wb') as output:
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_IMAGE:
                    raise ValueError('Verification image too large')
                output.write(chunk)


def image_payload(session, data, directory):
    # Import heavy image libraries only when verification is actually required.
    from PIL import Image
    from .captcha_support.image_recognition_v2 import find_gap_position
    from .captcha_support.restore_correct import restore_image_correct
    from .captcha_support.decode_o_string import decode_o_string
    from .captcha_support.trajectory_enhanced import generate_realistic_trajectory
    from .captcha_support.ac_encoder_full import generate_ac
    bg, slider = Path(directory)/'background.png', Path(directory)/'slider.png'
    download(session, data['p1'], bg)
    download(session, data['p2'], slider)
    with Image.open(bg) as image:
        width, height = image.size
        if width > 2048 or height > 2048:
            raise ValueError('Invalid verification image dimensions')
    order = data.get('o')
    if order:
        order = decode_o_string(order) if isinstance(order, str) else order
        if not isinstance(order, list) or not order or sorted(order) != list(range(len(order))) or len(order) > width:
            raise ValueError('Invalid image slice order')
        bg = Path(restore_image_correct(str(bg), order, width//len(order), debug=False))
    x, detected_y = find_gap_position(str(bg), str(slider), debug=False)
    y = int(data.get('y', detected_y))
    if not 0 <= x <= width or not 0 <= y <= height:
        raise ValueError('Invalid verification coordinates')
    trajectory = generate_realistic_trajectory(x)
    final_x, final_y = trajectory[-1][0], y + trajectory[-1][1]
    return {'ac': generate_ac(trajectory, final_x, final_y, sid=data['sid']),
            'x': final_x, 'y': final_y}


def _record(directory, payload, result):
    if os.environ.get('SAVE_CAPTCHA_IMAGES','false').lower() != 'true':
        return
    try:
        target=Path(os.environ.get('CAPTCHA_IMAGES_DIR','captcha_collection'))/uuid.uuid4().hex
        target.mkdir(parents=True,mode=0o700)
        for source in Path(directory).glob('*.png'):
            shutil.copyfile(source,target/source.name)
            os.chmod(target/source.name,0o600)
        reason=result.get('msg')
        reason=reason if reason in {'POSITION_MISMATCH','TIMEOUT','VERIFY_FAILED'} else '未通过' if not result.get('success') else 'None'
        record={'x':payload['x'],'y':payload['y'],'success':result.get('success') is True,'reason':reason}
        path=target/'info.json';path.write_text(json.dumps(record,ensure_ascii=False));os.chmod(path,0o600)
    except OSError:
        pass  # Optional local diagnostics must not change verification outcome.


def solve(user_agent, is_app=False):
    """Try one original-style challenge; return a request header value or None."""
    try:
        with requests.Session() as session, tempfile.TemporaryDirectory(prefix='longfor-captcha-') as directory:
            session.trust_env = False
            session.headers.update({'User-Agent': user_agent, 'Origin': 'https://longzhu.longfor.com',
                                    'Referer': 'https://longzhu.longfor.com/'})
            uv = _json(session.get('https://devops-prod.longfor.com/v2/api/uv/type',
                                  params={'appId':'LdIPdF3earg'}, timeout=(5,10), allow_redirects=False))
            if str(uv.get('code')) != '200' or uv.get('data') != 'c':
                return None
            challenge = secrets.token_hex(4) + ''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(32))
            aid = f'dx-{int(time.time()*1000)}-{secrets.randbelow(90000000)+10000000}-1'
            params = {'w':300,'h':150,'s':50,'ak':APP_ID,'c':challenge,'jsv':'1.3.41.372',
                      'aid':aid,'wp':1,'de':0,'uid':'','lf':0,'tpc':'','_r':random.random()}
            data = _json(session.get(VERIFY_BASE+'/api/a',params=params,timeout=(5,10),allow_redirects=False))
            if data.get('success') is not True or data.get('result') != 1 or not data.get('sid'):
                return None
            payload = image_payload(session, data, directory)
            payload.update(ak=APP_ID,c=challenge,uid='',jsv='1.3.41.372',sid=data['sid'],aid=aid)
            result = _json(session.post(VERIFY_BASE+'/api/v1',data=payload,timeout=(5,10),allow_redirects=False))
            _record(directory,payload,result)
            token = result.get('token')
            if result.get('success') is not True or not isinstance(token,str) or not token or len(token)>2048:
                return None
            if any(ord(c)<33 or ord(c)>126 for c in token):
                return None
            # Preserve the complete value returned by verification, including any suffix.
            # Do not synthesize or append a second challenge for either client.
            return token
    except Exception:
        # Do not reflect response bodies, image URLs, credentials or exception messages.
        return None
