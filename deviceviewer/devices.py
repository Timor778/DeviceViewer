from dataclasses import dataclass, asdict
import secrets
import time
import hid


@dataclass
class Battery:
    key: str
    name: str
    brand: str
    percent: int | None = None
    charging: bool = False
    detail: str = ''
    protocol: str = ''
    updated: float | None = None


def sony_request(tid):
    packet = bytearray(64)
    packet[:13] = bytes([2, 12, 1, 0, 0xFC, 8, 0x96, 0xC3, 0x41, 4, 1, tid & 255, tid >> 8])
    packet[13] = sum(packet[6:13]) & 255
    return bytes(packet)


def sony_response(data, tid):
    b = bytes(data)
    if len(b) < 16 or b[0] != 2 or not 14 <= b[1] <= 62 or len(b) < b[1] + 2:
        return None
    if b[2:4] != b'\x04\xff' or b[5:8] != b'\x00\x96\xc3' or b[8] >> 4 != 1:
        return None
    if b[9] != 4 or b[10] not in (0x10, 0xA0) or int.from_bytes(b[11:13], 'little') != tid:
        return None
    if sum(b[5:b[1]+1]) & 255 != b[b[1]+1]:
        return None
    if b[14] == 255:
        raise RuntimeError('耳机未开机或无线连接已断开')
    if b[14] > 100:
        raise RuntimeError('设备返回无效电量')
    return b[14], bool(b[13])


def read_sony(device):
    tid = secrets.randbelow(65534) + 2
    device.write(sony_request(tid))
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        result = sony_response(device.read(64, 250), tid)
        if result is not None:
            return result
    raise TimeoutError('耳机未响应，请确认已开机；也可退出 INZONE Hub 后重试')


class HidppError(RuntimeError):
    pass


class Hidpp:
    def __init__(self, device, index, long_report=True, software_id=None):
        self.device, self.index, self.long_report = device, index, long_report
        self.software_id = secrets.randbelow(15) + 1 if software_id is None else software_id
        self._features = {}

    def query(self, feature, function=0, params=b''):
        # Discard pending replies, then use a different nonzero software ID for
        # each transaction. ROOT replies don't echo their requested feature ID.
        for _ in range(32):
            if not self.device.read(64, 1):
                break
        self.software_id = self.software_id % 15 + 1
        function = (function & 0xF0) | self.software_id
        size, rid = (20, 0x11) if self.long_report else (7, 0x10)
        packet = (bytes([rid, self.index, feature, function]) + params).ljust(size, b'\0')
        if self.device.write(packet) != len(packet):
            raise OSError('无法发送电量查询')
        deadline = time.monotonic() + .65
        while time.monotonic() < deadline:
            b = bytes(self.device.read(64, 100))
            if not b or b[0] not in (0x10, 0x11):
                continue
            if len(b) < (7 if b[0] == 0x10 else 20) or b[1] != self.index:
                continue
            if b[2:4] == bytes([feature, function]):
                return b[4:]
            if b[2] in (0x8F, 0xFF) and b[3:5] == bytes([feature, function]):
                raise HidppError('设备拒绝电量查询，等待下次刷新')
        raise HidppError('设备响应超时，等待唤醒后刷新')

    def feature(self, number):
        if number in self._features:
            return self._features[number]
        for _ in range(2):
            try:
                reply = self.query(0, params=number.to_bytes(2, 'big'))
                index = reply[0]
                if not index:
                    return 0  # Explicitly absent, unlike a timeout/error.
                feature_set = index if number == 1 else self.feature(1)
                if not feature_set:
                    raise HidppError('设备缺少特性校验接口')
                identity = self.query(feature_set, 0x10, bytes([index]))
                if identity[:2] == number.to_bytes(2, 'big'):
                    self._features[number] = index
                    return index
            except HidppError:
                continue
        raise HidppError('设备响应与请求的电量协议不匹配，已忽略本次读数')

    def battery(self):
        for number, function in ((0x1004, 0x10), (0x1000, 0)):
            feature = self.feature(number)
            if not feature:
                continue
            previous = None
            for _ in range(3):
                try:
                    b = self.query(feature, function)
                except HidppError:
                    previous = None
                    continue
                if len(b) < 3 or not 0 < b[0] <= 100 or b[2] > 7:
                    previous = None
                    continue
                if number == 0x1004 and b[1] not in (0, 1, 2, 4, 8):
                    previous = None
                    continue
                reading = b[0], b[2]
                if reading == previous:
                    return b[0], b[2] in (1, 2, 4), f'HID++ · {number:04X}'
                previous = reading
            # Once a supported battery feature is found, an unreliable reading
            # is not a reason to reinterpret a different feature as legacy battery.
            raise HidppError('电量响应未确认一致，已忽略本次读数，等待下次刷新')
        raise RuntimeError('未收到电量；请移动鼠标唤醒后重试，或此型号需要另行适配')

    def name(self):
        idx = self.feature(5)
        if not idx:
            return None
        size = self.query(idx)
        if not size or not 0 < size[0] < 100:
            return None
        out = b''
        while len(out) < size[0]:
            b = self.query(idx, 0x10, bytes([len(out)]))
            if not b:
                return None
            out += b[:size[0]-len(out)]
        return out.decode('utf-8', errors='replace')


def scan():
    """Only known battery query protocols are transmitted; unknown HID is listed separately."""
    inventory = hid.enumerate()
    results = []
    logi = [d for d in inventory if d['vendor_id'] == 0x046D and d['usage_page'] == 0xFF00 and d['usage'] in (1, 2)]
    # Prefer the long-report collection; replies are routed to its own collection on Windows.
    long_paths = {d['path'].lower().split(b'&col')[0] for d in logi if d['usage'] == 2}
    candidates = [d for d in inventory if (d in logi and (d['usage'] == 2 or d['path'].lower().split(b'&col')[0] not in long_paths))
                  or (d['vendor_id'] == 0x054C and d['product_id'] == 0x0EBF and d['usage_page'] == 0xFF04)]
    for d in candidates:
        sony = d['vendor_id'] == 0x054C
        key = d['path'].decode(errors='replace')
        state = Battery(key, 'Sony INZONE H5' if sony else 'Logitech LIGHTSPEED', 'SONY' if sony else 'LOGITECH')
        device = hid.device()
        try:
            device.open_path(d['path'])
            if sony:
                state.percent, state.charging = read_sony(device)
                state.protocol = 'Sony HCI / HID'
            else:
                last_error = None
                for slot in (1, 0xFF):
                    try:
                        peer = Hidpp(device, slot, d['usage'] == 2)
                        state.percent, state.charging, state.protocol = peer.battery()
                        try:
                            state.name = peer.name() or state.name
                        except HidppError:
                            pass  # A name lookup failure must not invalidate a confirmed battery reading.
                        break
                    except RuntimeError as exc:
                        last_error = exc
                if state.percent is None:
                    raise last_error
            state.detail = '正在充电' if state.charging else '无线连接 · 电池供电'
            state.updated = time.time()
        except (OSError, RuntimeError) as exc:
            state.detail = str(exc) or '设备被其他软件占用或连接已断开'
        finally:
            device.close()
        results.append(state)
    return results, inventory


def diagnostic():
    states, inventory = scan()
    return {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'devices': [asdict(s) for s in states],
            'hid': [{k: (v.decode(errors='replace') if isinstance(v, bytes) else v) for k, v in d.items()} for d in inventory]}
