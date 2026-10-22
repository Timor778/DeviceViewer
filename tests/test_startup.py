import unittest
from unittest.mock import patch
import winreg

from deviceviewer import startup


class StartupTests(unittest.TestCase):
    @patch.object(startup.sys, 'frozen', True, create=True)
    @patch.object(startup.sys, 'executable', 'C:\\My Apps\\DeviceViewer.exe')
    def test_packaged_command_quotes_spaces_and_starts_in_background(self):
        self.assertEqual(startup.startup_command(), '"C:\\My Apps\\DeviceViewer.exe" --background')

    @patch.object(startup.sys, 'frozen', False, create=True)
    @patch.object(startup.sys, 'executable', 'C:\\Python Env\\python.exe')
    @patch.object(startup.Path, 'is_file', return_value=True)
    def test_source_command_uses_pythonw_and_absolute_script(self, exists):
        command = startup.startup_command()
        self.assertTrue(command.startswith('"C:\\Python Env\\pythonw.exe" '))
        self.assertIn(str(startup.Path(startup.__file__).resolve().parents[1] / 'main.py'), command)
        self.assertTrue(command.endswith(' --background'))

    @patch.object(startup, 'write_registration')
    @patch.object(startup, 'startup_command', return_value='app.exe --background')
    def test_enable_and_disable_only_current_app_entry(self, command, write):
        startup.set_enabled(True)
        write.assert_called_with(('app.exe --background', winreg.REG_SZ))
        startup.set_enabled(False)
        write.assert_called_with(None)

    @patch.object(startup, 'read_registration')
    @patch.object(startup, 'startup_command', return_value='app.exe --background')
    def test_setting_reflects_actual_registration(self, command, read):
        for entry, expected in ((None, False), (('other.exe', winreg.REG_SZ), False),
                                (('app.exe --background', winreg.REG_SZ), True)):
            read.return_value = entry
            self.assertEqual(startup.is_enabled(), expected)

    @patch.object(startup.winreg, 'OpenKey', side_effect=FileNotFoundError)
    def test_missing_startup_key_is_disabled(self, open_key):
        self.assertIsNone(startup.read_registration())
        startup.write_registration(None)

    @patch.object(startup.winreg, 'SetValueEx')
    @patch.object(startup.winreg, 'CreateKeyEx')
    def test_writes_current_user_run_key(self, create, write):
        startup.write_registration(('app.exe --background', winreg.REG_SZ))
        create.assert_called_once_with(winreg.HKEY_CURRENT_USER, startup.RUN_KEY, 0, winreg.KEY_SET_VALUE)
        write.assert_called_once_with(create.return_value.__enter__.return_value,
                                     'DeviceViewer', 0, winreg.REG_SZ, 'app.exe --background')

    @patch.object(startup.winreg, 'OpenKey', side_effect=PermissionError('denied'))
    def test_access_errors_are_not_silently_hidden(self, open_key):
        with self.assertRaises(PermissionError):
            startup.read_registration()


if __name__ == '__main__':
    unittest.main()
