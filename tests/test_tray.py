import queue
import threading
import unittest
from unittest.mock import Mock, patch

from deviceviewer.app import App
from deviceviewer.devices import Battery
from deviceviewer.display import battery_icon


class FakeNativeIcon:
    """Model native icon caching and the independent pystray setup thread."""
    def __init__(self, name, icon, title, menu):
        self.icon = icon
        self.title = title
        self.menu = menu
        self._visible = False
        self.native_image = None
        self.setup_finished = threading.Event()
        self.visible_threads = []

    def run(self, setup):
        setup(self)
        self.setup_finished.set()

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self.visible_threads.append(threading.get_ident())
        self._visible = value
        if value:
            self.native_image = self.icon.copy()

    def update_menu(self):
        pass


class TrayTests(unittest.TestCase):
    def app(self):
        app = App.__new__(App)
        app.events = queue.Queue()
        app.states = []
        app.config = {'tray_device': None, 'threshold': 50}
        app.root = Mock()
        return app

    @patch('deviceviewer.app.ImageTk.PhotoImage', return_value=object())
    @patch('deviceviewer.app.pystray.Icon', FakeNativeIcon)
    def test_setup_never_publishes_placeholder_from_background_thread(self, photo):
        app = self.app()
        ui_thread = threading.get_ident()
        app.create_tray()
        self.assertTrue(app.tray.setup_finished.wait(2))
        self.assertEqual(app.events.get_nowait(), ('tray_ready', None))
        self.assertFalse(app.tray.visible)
        self.assertIsNone(app.tray.native_image)
        # First battery reply can arrive before the UI processes tray_ready.
        app.states = [Battery('mouse', 'PRO X 2', 'LOGITECH', 47)]
        app.update_tray()
        app.show_tray()
        self.assertTrue(app.tray_ready)
        self.assertEqual(app.tray.visible_threads, [ui_thread])
        self.assertEqual(app.tray.native_image.tobytes(), battery_icon(47, True).tobytes())
        app.root.iconphoto.assert_called_with(True, app.window_icon)

    @patch('deviceviewer.app.ImageTk.PhotoImage', return_value=object())
    @patch('deviceviewer.app.pystray.Icon', FakeNativeIcon)
    def test_tray_ready_before_first_reading(self, photo):
        app = self.app()
        app.create_tray()
        self.assertTrue(app.tray.setup_finished.wait(2))
        app.show_tray()
        app.states = [Battery('mouse', 'PRO X 2', 'LOGITECH', 48)]
        app.update_tray()
        self.assertEqual(app._tray_appearance, (48, True))
        self.assertEqual(app.tray.icon.tobytes(), battery_icon(48, True).tobytes())


if __name__ == '__main__':
    unittest.main()
