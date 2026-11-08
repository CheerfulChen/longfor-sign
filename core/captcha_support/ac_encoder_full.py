import time

import base64

import random

from typing import List, Tuple

class ACEncoderFull:
    """完整的 AC 参数编码器"""

    # 自定义 Base64 字符表
    BASE64_CHARS = "XmYj3u1PnvisIZUF8ThR/a6DfO+kW4JHrCELycAzSxleoQp02MtwV9Nd57qGgbKB="

    def __init__(self, sid: str = ""):
        """初始化编码器"""
        self.sid = sid
        self._ua = b""
        self._sa = []
        self.tm = int(time.time() * 1000)

    # ============ 基础编码方法 ============

    def bs2(self, num: int) -> bytes:
        """将数字转换为2字节"""
        return bytes([(num >> 8) & 0xFF, num & 0xFF])

    def bs4(self, num: int) -> bytes:
        """将数字转换为4字节"""
        return self.bs2((num >> 16) & 0xFFFF) + self.bs2(num & 0xFFFF)

    def bs8(self, num: int) -> bytes:
        """将数字转换为8字节"""
        high = num // (2 ** 32)
        low = num % (2 ** 32)
        return self.bs4(high) + self.bs4(low)

    def bss(self, s: str) -> bytes:
        """将字符串转换为字节数组"""
        return s.encode('latin-1', errors='ignore')

    def btoa(self, data: bytes) -> str:
        """自定义 Base64 编码"""
        standard_b64 = base64.b64encode(data).decode('ascii')
        standard_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
        result = ""
        for char in standard_b64:
            idx = standard_chars.index(char)
            result += self.BASE64_CHARS[idx]
        return result

    # ============ 加密方法 ============

    def encryptTM(self, data: bytes) -> bytes:
        """加密时间戳"""
        result = bytearray()
        for byte in data:
            a = byte >> 4
            u = byte << 4
            c = (a + u + 15273) & 255
            result.append(c)
        return bytes(result)

    def encryptBR(self, data: bytes) -> bytes:
        """加密浏览器信息"""
        result = bytearray()
        key = 821
        for byte in data:
            u = key << 4 ^ key
            key = (240 & u) + (key >> 7)
            result.append(255 & (byte ^ key))
        return bytes(result)

    def encryptSC(self, data: bytes) -> bytes:
        """加密屏幕信息"""
        result = bytearray()
        key = 43221
        for i, byte in enumerate(data):
            c = byte ^ key
            key = key * i % 256 + 24671
            result.append(c & 255)
        return bytes(result)

    def encryptLO(self, data: bytes) -> bytes:
        """加密 URL 信息"""
        result = bytearray()
        key = 312
        for byte in data:
            a = key << 2 ^ key
            key = (240 & a) + (key >> 5)
            result.append(255 & (byte ^ key))
        return bytes(result)

    def encryptCF(self, data: bytes) -> bytes:
        """加密代码特征"""
        result = bytearray()
        key = 34313
        for byte in data:
            a = byte ^ key
            key = a
            result.append(255 & a)
        return bytes(result)

    def encryptDI(self, data: bytes) -> bytes:
        """加密开发者工具检测"""
        result = bytearray()
        key = 156
        for byte in data:
            u = key << 6 ^ key
            key = (240 & u) + (key >> 4)
            result.append((byte ^ key) & 255)
        return bytes(result)

    def encryptEM(self, data: bytes) -> bytes:
        """加密自动化检测"""
        result = bytearray()
        for byte in data:
            u = (byte - 6) & 255
            c = u >> 3
            f = u << 5
            s = (c + f) & 255
            result.append(s)
        return bytes(result)

    def encryptJSV(self, data: bytes) -> bytes:
        """加密 JS 版本"""
        result = bytearray()
        key_str = "VxMpoN86g7lA"
        key_idx = 32
        for byte in data:
            key_idx = (key_idx + 3) % len(key_str)
            encrypted = (byte ^ ord(key_str[key_idx])) & 255
            result.append(encrypted)
        return bytes(result)

    def encryptTK(self, data: bytes) -> bytes:
        """加密 token"""
        result = bytearray()
        key = 2422
        for byte in data:
            a = byte ^ key
            key += 2
            if key >= 2147483647:
                key = 2372
            result.append(a & 255)
        return bytes(result)

    def encryptSA(self, data: bytes) -> bytes:
        """加密轨迹数据"""
        result = bytearray()
        key = 33265
        for byte in data:
            encrypted = (byte ^ key) & 255
            result.append(encrypted)
            key = encrypted
        return bytes(result)

    def encryptTEMP(self, data: bytes) -> bytes:
        """加密 TEMP 数据"""
        result = bytearray()
        key_str = "C6Br4b6f7NgK"
        key_idx = 44
        for byte in data:
            key_idx = (key_idx + 4) % len(key_str)
            encrypted = (byte ^ ord(key_str[key_idx])) & 255
            result.append(encrypted)
        return bytes(result)

    # ============ 核心方法 ============

    def app(self, event_type: int, encrypted_data: bytes):
        """添加事件到 _ua"""
        header = bytes([event_type]) + self.bs2(len(encrypted_data))
        self._ua += header + encrypted_data

    # ============ 环境信息收集 ============

    def getTM(self):
        """事件 1: 时间戳"""
        tm_bytes = self.bs8(self.tm)
        encrypted = self.encryptTM(tm_bytes)
        self.app(1, encrypted)

    def getBR(self):
        """事件 2: 浏览器信息"""
        # 简化版：os=4(iPhone), browser=13(MicroMessenger), version=8
        os = 4
        browser = 13
        version = "8"
        data = bytes([os, browser]) + self.bs2(len(version)) + self.bss(version)
        encrypted = self.encryptBR(data)
        self.app(2, encrypted)

    def getSC(self):
        """事件 3: 屏幕信息"""
        # 简化版：iPhone 屏幕信息
        screen_data = [
            (375, 667),   # width, height
            (375, 667),   # availWidth, availHeight
            (0, 0),       # screenLeft, screenTop
            (375, 667),   # innerWidth, innerHeight
            (375, 667),   # outerWidth, outerHeight
        ]
        data = b""
        for w, h in screen_data:
            data += self.bs2(w) + self.bs2(h)
        encrypted = self.encryptSC(data)
        self.app(3, encrypted)

    def getLO(self):
        """事件 4: URL 信息"""
        # 简化版：当前 URL
        href = "https://longzhu.longfor.com/"
        referrer = ""
        data = self.bs2(len(href)) + self.bss(href) + self.bs2(len(referrer)) + self.bss(referrer)
        encrypted = self.encryptLO(data)
        self.app(4, encrypted)

    def getCF(self):
        """事件 5: 代码特征"""
        # 随机代码片段
        code_sample = "function(){return true;}"
        start_pos = 0
        length = min(10, len(code_sample))
        data = self.bs2(start_pos) + self.bs2(length) + self.bss(code_sample[start_pos:start_pos+length])
        encrypted = self.encryptCF(data)
        self.app(5, encrypted)

    def getDI(self):
        """事件 6: 开发者工具检测"""
        # 1 = 正常, 4 = IE devtools, 8 = 窗口异常
        di_value = 1
        data = bytes([di_value])
        encrypted = self.encryptDI(data)
        self.app(6, encrypted)

    def getEM(self):
        """事件 7: 自动化检测"""
        # 32位标志位，全0表示正常
        em_value = 0
        data = self.bs4(em_value)
        encrypted = self.encryptEM(data)
        self.app(7, encrypted)

    def getJSV(self):
        """事件 8: JS 版本"""
        jsv = 1  # greenseer.js 版本号
        data = self.bs4(jsv)
        encrypted = self.encryptJSV(data)
        self.app(8, encrypted)

    def getTK(self):
        """事件 9: token/sid"""
        if self.sid:
            data = self.bs2(len(self.sid)) + self.bss(self.sid)
            encrypted = self.encryptTK(data)
            self.app(9, encrypted)

    # ============ 轨迹处理 ============

    def recordSA(self, x: int, y: int, timestamp: int):
        """记录轨迹点"""
        relative_time = timestamp - self.tm
        data = self.bs4(relative_time) + self.bs2(x) + self.bs2(y)
        encrypted = self.encryptSA(data)
        self._sa.append(encrypted)

    def sendSA(self):
        """事件 17: 发送所有轨迹数据"""
        for sa_data in self._sa:
            self.app(17, sa_data)

    def sendTemp(self, temp_str: str):
        """事件 10: 发送 TEMP 数据"""
        temp_bytes = self.bss(temp_str)
        data = self.bs2(len(temp_str)) + temp_bytes
        encrypted = self.encryptTEMP(data)
        self.app(10, encrypted)

    def getUA(self) -> str:
        """生成最终的 AC 参数"""
        encoded = self.btoa(self._ua)
        return f"s_v3#{encoded}"

    # ============ 主流程 ============

    def start(self):
        """初始化：收集环境信息"""
        self.getTM()    # 1
        self.getBR()    # 2
        self.getLO()    # 4
        self.getCF()    # 5
        self.getDI()    # 6
        self.getEM()    # 7
        self.getJSV()   # 8
        self.getTK()    # 9
        self.getSC()    # 3

    def generate(self, trajectory: List[Tuple[int, int, int]], x: int, y: int) -> str:
        """
        生成完整的 AC 参数

        Args:
            trajectory: [(x, y, timestamp_ms), ...] 轨迹点列表
            x: 最终 x 坐标
            y: 最终 y 坐标

        Returns:
            AC 参数字符串
        """
        # 1. 收集环境信息
        self.start()

        # 2. 记录轨迹点
        for point_x, point_y, timestamp in trajectory:
            self.recordSA(point_x, point_y, timestamp)

        # 3. 发送轨迹数据
        self.sendSA()

        # 4. 发送 TEMP 数据
        temp_str = f"x={x}&y={y}"
        self.sendTemp(temp_str)

        # 5. 生成 UA
        return self.getUA()

def generate_ac(trajectory: List[Tuple[int, int, int]], x: int, y: int, sid: str = "") -> str:
    """生成 AC 参数（便捷函数）"""
    encoder = ACEncoderFull(sid)
    return encoder.generate(trajectory, x, y)
