"""Opt-in Windows GUI integration check: run from the repository root."""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deviceviewer.display import enable_dpi_awareness
from deviceviewer.app import App
from deviceviewer import startup
from pystray._util import win32

shell_calls = []
original_notify = win32.Shell_NotifyIcon


def record_notify(code, data):
    result = original_notify(code, data)
    shell_calls.append((code, data.uFlags, bool(result)))
    return result


win32.Shell_NotifyIcon = record_notify


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


enable_dpi_awareness()
# Exercise the real settings callbacks without changing the user's Run key.
registration = {'entry': None}
startup.read_registration = lambda: registration['entry']
startup.write_registration = lambda entry: registration.update(entry=entry)
app = App(background=True)
scratch = tempfile.TemporaryDirectory(prefix='deviceviewer-ui-', dir=Path(__file__).resolve().parents[1] / 'build')
app.config_path = Path(scratch.name) / 'settings.json'
app.config['alerts'] = False
errors = []


def callback_error(kind, error, traceback):
    errors.append(str(error))
    print('TK ERROR:', error, flush=True)


app.root.report_callback_exception = callback_error
app.root.after(30000, lambda: app.quit() if not app.closed else None)


def open_settings():
    assert app.root.state() == 'withdrawn', 'Background startup unexpectedly opened the main window'
    app.show()
    app.settings()
    app.root.after(500, verify)


def verify():
    try:
        assert app.states, 'No compatible devices found in live check'
        assert not any(isinstance(w, tk.Button) and w.cget('text') == '收起到托盘' for w in descendants(app.root))
        win = app.settings_window
        win.update_idletasks()
        all_widgets = list(descendants(win))
        assert not any(isinstance(w, tk.Checkbutton) and '置顶' in w.cget('text') for w in all_widgets)
        assert not bool(app.root.attributes('-topmost')), 'Window unexpectedly stays on top'
        threshold, tray = [w for w in all_widgets if isinstance(w, ttk.Combobox)]
        autostart = next(w for w in all_widgets if isinstance(w, tk.Checkbutton) and '开机自启动' in w.cget('text'))
        assert not startup.is_enabled(), 'Startup should be off by default'
        autostart.invoke()
        assert tuple(map(int, threshold['values'])) == (10, 20, 30, 40, 50)
        assert threshold.get() == str(app.config['threshold'])
        threshold.set('30')
        device_list = next(w for w in all_widgets if isinstance(w, tk.Listbox))
        original_keys = [s.key for s in app.states]
        if len(original_keys) > 1:
            device_list.selection_clear(0, 'end')
            device_list.selection_set(0)
            next(w for w in all_widgets if isinstance(w, tk.Button) and w.cget('text') == '↓ 下移').invoke()
        # Explicit choice is independent of the order being edited.
        tray.current(1)
        save = next(w for w in all_widgets if isinstance(w, tk.Button) and w.cget('text') == '保存设置')
        assert save.winfo_y() + save.winfo_height() <= win.winfo_height(), 'Save button clipped'
        save.invoke()
        assert startup.is_enabled(), 'Startup checkbox was not applied on save'
        assert registration['entry'][0].endswith(' --background')
        saved = json.loads(app.config_path.read_text(encoding='utf-8'))
        assert saved['threshold'] == 30
        assert saved['tray_device'] == original_keys[0]
        if len(original_keys) > 1:
            assert saved['device_order'][:2] == original_keys[1::-1]
            assert app.states[0].key == original_keys[1]
        assert app.tray_ready, 'Native tray not ready'
        assert app.tray.visible and app.tray._icon_valid, 'Native icon was not published'
        assert any(code == win32.NIM_ADD and ok for code, flags, ok in shell_calls), 'Windows rejected tray creation'
        assert any(code == win32.NIM_MODIFY and flags & win32.NIF_ICON and ok
                   for code, flags, ok in shell_calls), 'Windows rejected numeric icon update'
        assert app._tray_appearance[0] is not None, 'Tray still contains unknown battery placeholder'
        app.settings()
        controls = [w for w in descendants(app.settings_window) if isinstance(w, ttk.Combobox)]
        assert controls[0].get() == '30', 'Threshold was not restored'
        assert controls[1].current() > 0, 'Selected tray device was not restored'
        widgets = list(descendants(app.settings_window))
        autostart = next(w for w in widgets if isinstance(w, tk.Checkbutton) and '开机自启动' in w.cget('text'))
        assert app.root.getvar(autostart.cget('variable')) == 1, 'Startup checkbox was not restored'
        autostart.invoke()
        save = next(w for w in widgets if isinstance(w, tk.Button) and w.cget('text') == '保存设置')
        with patch.object(app, 'save_config', side_effect=PermissionError('test: configuration is read-only')):
            with patch('deviceviewer.app.messagebox.showerror') as error_dialog:
                save.invoke()
                assert error_dialog.called, 'Save failure was hidden'
        assert startup.is_enabled(), 'Failed settings save did not restore previous startup registration'
        save.invoke()
        assert registration['entry'] is None, 'Startup checkbox did not remove registration'
        print(json.dumps({'dpi': app.dpi, 'scale': app.scale,
                          'devices': [(s.name, s.percent) for s in app.states],
                          'tray_ready': app.tray_ready, 'settings_saved': True}, ensure_ascii=False), flush=True)
        print('Windows Shell accepted numeric tray updates:', shell_calls, flush=True)
    except Exception as exc:
        errors.append(str(exc))
        print('FAILED:', repr(exc), flush=True)
    finally:
        app.root.after(15000, app.quit)


app.root.after(2500, open_settings)
app.run()
scratch.cleanup()
if errors:
    raise SystemExit(1)
