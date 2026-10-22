import unittest
from unittest.mock import Mock
from deviceviewer.devices import sony_request, sony_response, Hidpp, HidppError


def event(percent=48, charger=0, tid=42):
    b = bytearray(64)
    b[:15] = bytes([2, 14, 4, 255, 10, 0, 0x96, 0xc3, 0x14, 4, 0x10, tid & 255, tid >> 8, charger, percent])
    b[15] = sum(b[5:15]) & 255
    return b


class FakeHid:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.sent = []
        self.pending = []

    def write(self, data):
        self.sent.append(data)
        self.pending.extend(self.replies)
        return len(data)

    def read(self, size, timeout):
        return self.pending.pop(0) if self.pending else []


def report(payload):
    return bytes(payload).ljust(20, b'\0')


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
        h = FakeHid([report([0x11, 1, 6, 0x1b, 99, 0, 0]), report([0x11, 1, 6, 0x1a, 48, 4, 0])])
        self.assertEqual(Hidpp(h, 1, software_id=9).query(6, 0x10)[:3], bytes([48, 4, 0]))
        self.assertEqual(len(h.sent[0]), 20)

    def test_logitech_discovery_and_battery(self):
        peer = Hidpp(FakeHid([]), 1)
        peer.query = Mock(side_effect=[bytes([6, 0, 5]), bytes([1, 0, 0]),
                                      bytes([0, 1, 0]), bytes([0x10, 4, 0]),
                                      bytes([48, 4, 1]), bytes([48, 4, 1])])
        self.assertEqual(peer.battery()[:2], (48, True))

    def test_logitech_error_response(self):
        h = FakeHid([report([0x11, 1, 0xff, 0, 0x0a, 1, 0])])
        with self.assertRaises(HidppError):
            Hidpp(h, 1, software_id=9).query(0)

    def test_stale_root_reply_is_discarded_before_next_request(self):
        h = FakeHid([report([0x11, 1, 0, 0x0b, 0, 0, 0])])
        h.pending = [report([0x11, 1, 0, 0x0a, 6, 0, 5])]
        peer = Hidpp(h, 1, software_id=10)
        self.assertEqual(peer.query(0, params=b'\x10\x00')[0], 0)
        self.assertEqual(h.sent[0][3], 0x0b)

    def test_report_id_and_length_are_validated(self):
        h = FakeHid([bytes([0x99, 1, 6, 0x1a, 15, 0, 4]),
                     bytes([0x11, 1, 6, 0x1a, 15, 0, 4]),
                     report([0x11, 1, 6, 0x1a, 47, 4, 0])])
        self.assertEqual(Hidpp(h, 1, software_id=9).query(6, 0x10)[:3], bytes([47, 4, 0]))

    def test_unified_capabilities_cannot_masquerade_as_legacy_battery(self):
        peer = Hidpp(FakeHid([]), 1)
        def query(feature, function=0, params=b''):
            if feature == 0:
                return {b'\x10\x04': b'\x00\x00\x00',
                        b'\x10\x00': b'\x06\x00\x05',  # Stale index for unified battery.
                        b'\x00\x01': b'\x01\x00\x00'}[params]
            if feature == 1:
                return b'\x00\x01\x00' if params == b'\x01' else b'\x10\x04\x00'
            if feature == 6 and function == 0:
                return b'\x0f\x00\x04'  # The old parser would show 15%, charging.
            raise AssertionError('Unexpected query')
        peer.query = Mock(side_effect=query)
        with self.assertRaises(HidppError):
            peer.battery()
        self.assertFalse(any(call.args[:2] == (6, 0) or call.args == (6,)
                             for call in peer.query.call_args_list))

    def test_timeout_is_not_a_reason_to_switch_battery_protocol(self):
        peer = Hidpp(FakeHid([]), 1)
        peer.feature = Mock(return_value=6)
        peer.query = Mock(side_effect=HidppError('timeout'))
        with self.assertRaises(HidppError):
            peer.battery()
        peer.feature.assert_called_once_with(0x1004)

    def test_single_false_charging_reading_is_not_published(self):
        peer = Hidpp(FakeHid([]), 1)
        peer.feature = Mock(return_value=6)
        peer.query = Mock(side_effect=[b'\x0f\x00\x04', b'\x2f\x04\x00', b'\x2f\x04\x00'])
        self.assertEqual(peer.battery()[:2], (47, False))

    def test_conflicting_responses_are_rejected(self):
        peer = Hidpp(FakeHid([]), 1)
        peer.feature = Mock(return_value=6)
        peer.query = Mock(side_effect=[b'\x0f\x00\x04', b'\x2f\x04\x00', b'\x0f\x00\x04'])
        with self.assertRaises(HidppError):
            peer.battery()

    def test_real_fifteen_percent_charging_is_not_hardcoded_away(self):
        peer = Hidpp(FakeHid([]), 1)
        peer.feature = Mock(return_value=6)
        peer.query = Mock(return_value=b'\x0f\x02\x01')
        self.assertEqual(peer.battery()[:2], (15, True))

    def test_confirmed_legacy_feature_still_works(self):
        peer = Hidpp(FakeHid([]), 1)
        peer.query = Mock(side_effect=[b'\0\0\0', b'\x08\0\0', b'\x01\0\0',
                                      b'\0\x01\0', b'\x10\0\0', b'\x2c\x20\0', b'\x2c\x20\0'])
        self.assertEqual(peer.battery(), (44, False, 'HID++ · 1000'))

    def test_software_identifier_changes_and_never_uses_notification_id(self):
        h = FakeHid([])
        def respond(packet):
            h.sent.append(packet)
            h.pending.append(report([packet[0], packet[1], packet[2], packet[3], 1, 0, 0]))
            return len(packet)
        h.write = respond
        peer = Hidpp(h, 1, software_id=14)
        for _ in range(16):
            peer.query(0)
        ids = [p[3] & 15 for p in h.sent]
        self.assertNotIn(0, ids)
        self.assertTrue(all(a != b for a, b in zip(ids, ids[1:])))


if __name__ == '__main__':
    unittest.main()
