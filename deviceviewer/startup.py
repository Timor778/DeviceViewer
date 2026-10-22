"""Opt-in startup for the current Windows user; no administrator rights needed."""
from pathlib import Path
import subprocess
import sys
import winreg

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'DeviceViewer'


def startup_command():
    if getattr(sys, 'frozen', False):
        args = [str(Path(sys.executable).absolute())]
    else:
        python = Path(sys.executable).absolute()
        pythonw = python.with_name('pythonw.exe')
        if pythonw.is_file():
            python = pythonw
        args = [str(python), str(Path(__file__).resolve().parents[1] / 'main.py')]
    return subprocess.list2cmdline(args + ['--background'])


def read_registration():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None


def write_registration(entry):
    if entry is None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
    else:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, entry[1], entry[0])


def is_enabled():
    entry = read_registration()
    return entry is not None and entry == (startup_command(), winreg.REG_SZ)


def set_enabled(enabled):
    write_registration((startup_command(), winreg.REG_SZ) if enabled else None)
