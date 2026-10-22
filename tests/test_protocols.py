import unittest
from deviceviewer.devices import sony_request, sony_response, Hidpp


def event(percent=48, charger=0, tid=42):
    b = bytearray(64)
    b[:15] = bytes([2, 14, 4, 255, 10, 0, 0x96, 0xc3, 0x14, 4, 0x10, tid & 255, tid >> 8, charger, percent])
    b[15] = sum(b[5:15]) & 255
    return b


class FakeHid:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.sent = []

    def write(self, data):
        self.sent.append(data)
        return len(data)

    def read(self, size, timeout):
        return next(self.replies, [])


class ProtocolTests(unittest.TestCase):
    def test_sony_read_only_packet(self):
        packet = sony_request(42)
        self.assertEqual(len(packet), 64)
        self.assertEqual(packet[8:13], bytes([0x41, 4, 1, 42, 0]))
        self.assertEqual(packet[13], sum(packet[6:13]) & 255)

    def test_sony_validation(self):
        self.assertEqual(sony_response(event(), 42), (48, False))
        self.assertEqual(sony_response(event(0, 1), 42), (0, True))
        self.assertEqual(sony_response(event(100), 42), (100, False))
        self.assertIsNone(sony_response(event(), 43))
        b = event()
        b[15] ^= 1
        self.assertIsNone(sony_response(b, 42))
        self.assertIsNone(sony_response(b[:10], 42))
        with self.assertRaises(RuntimeError):
            sony_response(event(255), 42)
        with self.assertRaises(RuntimeError):
            sony_response(event(101), 42)

    def test_logitech_filters_other_clients(self):
        h = FakeHid([bytes([0x11, 1, 6, 0x1b, 99, 0, 0]), bytes([0x11, 1, 6, 0x1a, 48, 4, 0])])
        self.assertEqual(Hidpp(h, 1).query(6, 0x10), bytes([48, 4, 0]))
        self.assertEqual(len(h.sent[0]), 20)

    def test_logitech_discovery_and_battery(self):
        h = FakeHid([bytes([0x11, 1, 0, 0x0a, 6, 0, 5]), bytes([0x11, 1, 6, 0x1a, 48, 4, 1])])
        self.assertEqual(Hidpp(h, 1).battery()[:2], (48, True))

    def test_logitech_error_response(self):
        h = FakeHid([bytes([0x11, 1, 0xff, 0, 0x0a, 1, 0])])
        self.assertIsNone(Hidpp(h, 1).query(0))


if __name__ == '__main__':
    unittest.main()
