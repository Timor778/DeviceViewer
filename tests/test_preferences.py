import unittest
from deviceviewer.devices import Battery
from deviceviewer.preferences import normalize_config, ordered_devices, selected_device, is_low, THRESHOLDS
from deviceviewer.display import battery_icon


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.mouse = Battery('mouse', 'PRO X 2', 'LOGITECH', 48)
        self.headset = Battery('headset', 'INZONE H5', 'SONY', 100)

    def test_old_settings_get_default_threshold(self):
        config = normalize_config({'interval': 30, 'alerts': True})
        self.assertEqual(config['threshold'], 50)
        self.assertIsNone(config['tray_device'])
        self.assertEqual(normalize_config({'interval': None, 'threshold': 25})['interval'], 30)
        self.assertEqual(normalize_config({'threshold': 25})['threshold'], 50)

    def test_retired_topmost_setting_is_ignored(self):
        self.assertNotIn('topmost', normalize_config({'topmost': True}))

    def test_threshold_is_strict_and_charging_does_not_alert(self):
        for threshold in THRESHOLDS:
            self.mouse.percent = threshold
            self.assertFalse(is_low(self.mouse, threshold))
            self.mouse.percent -= 1
            self.assertTrue(is_low(self.mouse, threshold))
            self.mouse.charging = True
            self.assertFalse(is_low(self.mouse, threshold))
            self.mouse.charging = False
        self.mouse.percent = None
        self.assertFalse(is_low(self.mouse, 50))

    def test_reordering_drives_default_tray_device(self):
        devices = ordered_devices([self.mouse, self.headset], ['headset', 'mouse'])
        self.assertIs(selected_device(devices, None), self.headset)
        self.assertIs(selected_device(devices, 'mouse'), self.mouse)
        self.assertIs(selected_device(devices, 'unplugged'), self.headset)
        self.assertIsNone(selected_device([], None))

    def test_new_devices_follow_saved_order(self):
        devices = ordered_devices([self.mouse, self.headset], ['headset'])
        self.assertEqual([s.key for s in devices], ['headset', 'mouse'])

    def test_tray_numbers_include_zero_and_unknown(self):
        for value in (None, 0, 9, 48, 100):
            image = battery_icon(value)
            self.assertEqual(image.size, (128, 128))
            self.assertEqual(image.mode, 'RGBA')
        self.assertNotEqual(battery_icon(0).tobytes(), battery_icon(None).tobytes())


if __name__ == '__main__':
    unittest.main()
