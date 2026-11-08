"""Small private OBS JSON store. Requires serialized FunctionGraph invocations."""
import base64
import hashlib
import hmac
import json
import os
import re
from email.utils import formatdate
from urllib.parse import quote
from xml.etree import ElementTree

import requests


def _error_details(response):
    """Expose only known error codes and request IDs, never an OBS error body.

    Signature error bodies may echo access keys, signatures and StringToSign
    (which contains the temporary security token).
    """
    codes = {
        'AccessDenied', 'SignatureDoesNotMatch', 'InvalidAccessKeyId',
        'InvalidSecurity', 'InvalidToken', 'ExpiredToken', 'SecurityTokenExpired',
        'RequestTimeTooSkewed', 'RequestExpired', 'NoSuchKey', 'NoSuchBucket',
        'AuthorizationHeaderMalformed', 'InvalidArgument', 'PermanentRedirect',
        'TemporaryRedirect', 'ServiceUnavailable', 'InternalError', 'InvalidRequest',
    }
    code, request_id = 'UnknownError', 'unavailable'
    body = response.text
    if not isinstance(body, str) or len(body) > 65536:
        return code, request_id
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return code, request_id
    for node in root.iter():
        tag = node.tag.rsplit('}', 1)[-1]
        value = (node.text or '').strip()
        if tag == 'Code' and value in codes:
            code = value
        elif tag == 'RequestId' and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
            request_id = value
    return code, request_id


class ObsStore:
    def __init__(self, context):
        self.bucket = os.environ.get('SIGN_OBS_BUCKET', '').strip()
        self.endpoint = os.environ.get('SIGN_OBS_ENDPOINT', 'obs.cn-east-3.myhuaweicloud.com').strip()
        self.prefix = os.environ.get('SIGN_OBS_PREFIX', 'longfor-sign').strip('/')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', self.bucket):
            raise ValueError('请配置有效的 SIGN_OBS_BUCKET')
        if not re.fullmatch(r'obs\.[a-z0-9-]+\.myhuaweicloud\.com', self.endpoint):
            raise ValueError('SIGN_OBS_ENDPOINT 应为 obs.<区域>.myhuaweicloud.com，不带协议')
        if not re.fullmatch(r'[a-zA-Z0-9/_-]+', self.prefix):
            raise ValueError('SIGN_OBS_PREFIX 只支持字母、数字、斜杠、下划线和短横线')
        if context is None:
            raise ValueError('OBS 存储需要函数访问委托及运行上下文')
        self.ak = context.getSecurityAccessKey()
        self.sk = context.getSecuritySecretKey()
        self.token = context.getSecurityToken()
        if not all((self.ak, self.sk, self.token)):
            raise ValueError('请为函数配置具有 OBS 读写权限的委托')

    def _request(self, method, day, value=None):
        key = '{}/{}.json'.format(self.prefix, day)
        path = quote(key, safe='/')
        headers = {'Date': formatdate(usegmt=True), 'x-obs-security-token': self.token}
        payload = None
        if value is not None:
            payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
            headers['Content-MD5'] = base64.b64encode(hashlib.md5(payload).digest()).decode()
        canonical = 'x-obs-security-token:{}\n'.format(self.token)
        string_to_sign = '{}\n{}\n{}\n{}\n{}{}/{}'.format(
            method, headers.get('Content-MD5', ''), headers.get('Content-Type', ''),
            headers['Date'], canonical, '/' + self.bucket, path)
        signature = base64.b64encode(hmac.new(self.sk.encode(), string_to_sign.encode(), hashlib.sha1).digest()).decode()
        headers['Authorization'] = 'OBS {}:{}'.format(self.ak, signature)
        try:
            response = requests.request(method, 'https://{}.{}/{}'.format(self.bucket, self.endpoint, path),
                                        headers=headers, data=payload, timeout=(5, 15), allow_redirects=False)
        except requests.RequestException:
            raise RuntimeError('OBS 网络请求失败') from None
        if not 200 <= response.status_code < 300:
            code, request_id = _error_details(response)
            if method == 'GET' and response.status_code == 404 and code == 'NoSuchKey':
                return None
            hints = {
                'AccessDenied': '检查执行委托的 GetObject、PutObject、ListBucket 权限及桶策略；权限更新可能尚未生效',
                'SignatureDoesNotMatch': 'OBS 请求签名不匹配，需要检查签名实现及区域地址',
                'InvalidAccessKeyId': '执行委托临时 AK 无效',
                'InvalidToken': '执行委托临时安全令牌无效',
                'ExpiredToken': '执行委托临时凭证已过期',
                'SecurityTokenExpired': '执行委托临时安全令牌已过期',
                'RequestTimeTooSkewed': '函数运行时钟与 OBS 时间偏差过大',
                'NoSuchBucket': 'SIGN_OBS_BUCKET 指定的桶不存在或区域不正确',
            }
            raise RuntimeError('OBS {} 失败，HTTP {}；Code={}；RequestId={}；{}'.format(
                method, response.status_code, code, request_id,
                hints.get(code, '检查 OBS 错误码和区域配置')))
        return response.json() if method == 'GET' else None

    def load(self, day):
        return self._request('GET', day)

    def save(self, day, state):
        self._request('PUT', day, state)
