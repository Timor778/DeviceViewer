import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import asdict

import pystray
from PIL import ImageTk
from .devices import scan
from .display import battery_icon, window_dpi
from .preferences import normalize_config, ordered_devices, selected_device, is_low, THRESHOLDS
from . import startup

BG = '#10141e'
CARD = '#1b2231'
FG = '#edf2fa'
MUTED = '#92a1b8'
GREEN = '#65e3bc'
BLUE = '#81aaff'


class App:
    def __init__(self, background=False):
        self.root = tk.Tk()
        if background:
            self.root.withdraw()
        self.dpi = window_dpi(self.root)
        self.scale = self.dpi / 96
        self.root.tk.call('tk', 'scaling', self.dpi / 72)
        self.root.title('DeviceViewer · 外设电量')
        self.root.geometry(f'{self.px(960)}x{self.px(700)}')
        self.root.minsize(self.px(760), self.px(580))
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self.hide)
        self.events = queue.Queue()
        self.states = []
        self.inventory = []
        self.busy = False
        self.closed = False
        self.alerted = set()
        self.next_scan = 0
        self.config_path = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'DeviceViewer' / 'settings.json'
        saved = {}
        try:
            saved = json.loads(self.config_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        self.config = normalize_config(saved)
        self.build()
        self.create_tray()
        self.refresh()
        self.root.after(150, self.tick)

    def px(self, value):
        return round(value * self.scale)

    def scale_widgets(self, widget):
        """Scale pixel dimensions once; point fonts use Tk's native DPI scaling."""
        if not getattr(widget, '_dpi_scaled', False):
            widget._dpi_scaled = True
            options = widget.keys()
            for key in ('padx', 'pady', 'wraplength', 'highlightthickness'):
                if key in options:
                    widget.configure(**{key: self.px(widget.winfo_pixels(widget.cget(key)))})
            if isinstance(widget, (tk.Canvas, tk.Scrollbar)):
                for key in ('width', 'height'):
                    if key in options:
                        widget.configure(**{key: self.px(widget.winfo_pixels(widget.cget(key)))})
            if isinstance(widget, tk.Canvas):
                widget.scale('all', 0, 0, self.scale, self.scale)
                for item in widget.find_all():
                    if widget.type(item) in ('oval', 'arc'):
                        widget.itemconfigure(item, width=self.px(float(widget.itemcget(item, 'width'))))
            if widget.winfo_manager() == 'pack':
                info = widget.pack_info()
                for key in ('padx', 'pady', 'ipadx', 'ipady'):
                    value = info[key]
                    parts = (value,) if isinstance(value, (int, float)) else widget.tk.splitlist(value)
                    widget.pack_configure(**{key: tuple(self.px(widget.winfo_pixels(v)) for v in parts)})
        for child in widget.winfo_children():
            if not isinstance(child, tk.Toplevel):
                self.scale_widgets(child)

    def save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')

    def label(self, parent, text, size=11, color=FG, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent['bg'], fg=color,
                        font=('Microsoft YaHei UI', size, 'bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, command, accent=False):
        return tk.Button(parent, text=text, command=command, bg=GREEN if accent else '#252f43',
                         fg=BG if accent else FG, activebackground='#a5f2d9' if accent else '#34435f',
                         activeforeground=BG if accent else FG, relief='flat', bd=0, padx=18, pady=10,
                         cursor='hand2', font=('Microsoft YaHei UI', 10, 'bold'))

    def build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill='x', padx=32, pady=(26, 20))
        self.label(header, '◉  DeviceViewer', 20, bold=True).pack(side='left')
        self.button(header, '设置', self.settings).pack(side='right')
        intro = tk.Frame(self.root, bg=BG)
        intro.pack(fill='x', padx=32)
        self.label(intro, '你的无线设备，一眼掌握。', 24, bold=True).pack(anchor='w')
        self.label(intro, '统一查看外设电量，让充电心中有数。', 11, MUTED).pack(anchor='w', pady=(8, 18))
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill='x', padx=32, pady=(0, 18))
        self.summary = self.label(bar, '正在连接设备…', 11, GREEN)
        self.summary.pack(side='left')
        self.refresh_button = self.button(bar, '↻  刷新电量', self.refresh, True)
        self.refresh_button.pack(side='right')
        area = tk.Frame(self.root, bg=BG)
        area.pack(fill='both', expand=True, padx=32)
        self.canvas = tk.Canvas(area, bg=BG, highlightthickness=0)
        scroll = tk.Scrollbar(area, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.cards = tk.Frame(self.canvas, bg=BG)
        self.cards_window = self.canvas.create_window(0, 0, anchor='nw', window=self.cards)
        self.cards.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.cards_window, width=e.width))
        self.root.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units'))
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill='x', padx=32, pady=(16, 22))
        self.status = self.label(bottom, '正在读取真实设备电量', 9, MUTED)
        self.status.pack(side='left')
        self.button(bottom, '设备与诊断', self.diagnostics).pack(side='right')
        self.render()
        self.scale_widgets(self.root)

    def render(self):
        for child in self.cards.winfo_children():
            child.destroy()
        if not self.states:
            frame = tk.Frame(self.cards, bg=CARD, padx=28, pady=36)
            frame.pack(fill='x')
            self.label(frame, '等待无线设备', 18, bold=True).pack(anchor='w')
            self.label(frame, '请插入接收器并开启外设，然后刷新电量。\n当前支持罗技 HID++ 电量设备与 Sony INZONE H5。',
                       11, MUTED, justify='left').pack(anchor='w', pady=(12, 0))
        for s in self.states:
            color = BLUE if s.brand == 'SONY' else GREEN
            if is_low(s, self.config['threshold']):
                color = '#ffbd70'
            frame = tk.Frame(self.cards, bg=CARD, padx=24, pady=18)
            frame.pack(fill='x', pady=(0, 14))
            ring = tk.Canvas(frame, width=132, height=132, bg=CARD, highlightthickness=0)
            ring.pack(side='right', padx=(20, 0))
            ring.create_oval(12, 12, 120, 120, outline='#303b50', width=8)
            if s.percent:
                ring.create_arc(12, 12, 120, 120, start=90, extent=-359.9*s.percent/100,
                                style='arc', outline=color, width=8)
            ring.create_text(66, 60, text=f'{s.percent}%' if s.percent is not None else '—', fill=FG,
                             font=('Segoe UI', 24, 'bold'))
            ring.create_text(66, 88, text='充电中' if s.charging else ('剩余电量' if s.percent is not None else '未读取'),
                             fill=MUTED, font=('Microsoft YaHei UI', 9))
            left = tk.Frame(frame, bg=CARD)
            left.pack(side='left', fill='both', expand=True)
            self.label(left, s.brand + '   /   2.4 GHz', 9, color, True).pack(anchor='w')
            self.label(left, s.name, 19, bold=True).pack(anchor='w', pady=(8, 8))
            self.label(left, s.detail, 10, MUTED, wraplength=460, justify='left').pack(anchor='w')
            if s.updated:
                self.label(left, s.protocol + '    ·    ' + time.strftime('%H:%M:%S', time.localtime(s.updated)),
                           9, MUTED).pack(anchor='w', pady=(8, 0))
        available = sum(s.percent is not None for s in self.states)
        self.summary.configure(text=f'●  {available} 台电量已读取   /   {len(self.states)} 台兼容设备')
        self.scale_widgets(self.cards)

    def refresh(self):
        if self.busy or self.closed:
            return
        self.busy = True
        self.refresh_button.configure(state='disabled', text='正在读取…')
        self.status.configure(text='正在查询设备，请稍候…')
        def work():
            try:
                self.events.put(('scan', scan()))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def tick(self):
        if self.closed:
            return
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'scan':
                    self.states, self.inventory = data
                    self.states = ordered_devices(self.states, self.config['device_order'])
                    self.render()
                    self.status.configure(text=f'更新于 {time.strftime("%H:%M:%S")}  ·  每 {self.config["interval"]} 秒刷新')
                    self.update_tray()
                    for s in self.states:
                        if s.percent is not None:
                            if is_low(s, self.config['threshold']) and s.key not in self.alerted and self.config['alerts']:
                                try:
                                    self.tray.notify(f'{s.name} 剩余 {s.percent}%，低于 {self.config["threshold"]}%，请及时充电。', '外设电量不足')
                                    self.alerted.add(s.key)
                                except OSError:
                                    pass
                            elif not is_low(s, self.config['threshold']):
                                self.alerted.discard(s.key)
                elif kind == 'error':
                    self.status.configure(text='读取失败：' + data)
                elif kind == 'show':
                    self.show()
                    continue
                elif kind == 'quit':
                    self.quit()
                    return
                elif kind == 'refresh':
                    self.refresh()
                    continue
                elif kind == 'select_device':
                    self.config['tray_device'] = data
                    try:
                        self.save_config()
                    except OSError as exc:
                        self.status.configure(text='设置保存失败：' + str(exc))
                    self.update_tray()
                    continue
                elif kind == 'tray_ready':
                    # The pystray setup callback runs in a separate thread. Only
                    # this Tk thread may publish images or show the native icon,
                    # so startup cannot cache a placeholder over the first reading.
                    try:
                        self.show_tray()
                    except OSError as exc:
                        self.tray_ready = False
                        self.show()
                        self.status.configure(text='托盘图标创建失败：' + str(exc))
                    continue
                elif kind == 'tray_error':
                    self.tray_ready = False
                    self.show()
                    self.status.configure(text='系统托盘不可用，可继续在窗口查看电量')
                    continue
                self.busy = False
                self.next_scan = time.monotonic() + self.config['interval']
                self.refresh_button.configure(state='normal', text='↻  刷新电量')
        except queue.Empty:
            pass
        if not self.busy and time.monotonic() >= self.next_scan:
            self.refresh()
        current_dpi = window_dpi(self.root)
        if current_dpi != self.dpi and self.root.state() != 'withdrawn':
            self.dpi = current_dpi
            self.scale = self.dpi / 96
            self.root.tk.call('tk', 'scaling', self.dpi / 72)
            for child in self.root.winfo_children():
                if not isinstance(child, tk.Toplevel):
                    child.destroy()
            self.root._dpi_scaled = False
            self.root.minsize(self.px(760), self.px(580))
            self.build()
            self.update_tray()
        self.root.after(150, self.tick)

    def create_tray(self):
        self.tray = pystray.Icon('DeviceViewer', battery_icon(None), 'DeviceViewer · 外设电量', self.tray_menu())
        self.tray_ready = False
        def ready(icon):
            self.events.put(('tray_ready', None))
        def run():
            try:
                self.tray.run(setup=ready)
            except Exception:
                self.events.put(('tray_error', None))
        threading.Thread(target=run, daemon=True).start()

    def show_tray(self):
        self.update_tray(force=True)
        self.tray.visible = True
        self.tray_ready = True

    def tray_menu(self):
        def choose(key):
            return lambda: self.events.put(('select_device', key))
        entries = [pystray.MenuItem('跟随列表第一个设备', choose(None),
                                    checked=lambda item: self.config['tray_device'] is None, radio=True)]
        for s in self.states:
            entries.append(pystray.MenuItem(s.name, choose(s.key), radio=True,
                           checked=lambda item, key=s.key: self.config['tray_device'] == key))
        return pystray.Menu(
            pystray.MenuItem('显示电量', lambda: self.events.put(('show', None)), default=True),
            pystray.MenuItem('托盘显示设备', pystray.Menu(*entries)),
            pystray.MenuItem('刷新', lambda: self.events.put(('refresh', None))),
            pystray.MenuItem('退出', lambda: self.events.put(('quit', None))))

    def update_tray(self, force=False):
        selected = selected_device(self.states, self.config['tray_device'])
        value = selected.percent if selected else None
        # Avoid replacing the native icon on every poll when the number has not changed.
        appearance = (value, is_low(selected, self.config['threshold']) if selected else False)
        if force or appearance != getattr(self, '_tray_appearance', None):
            image = battery_icon(*appearance)
            # Keep both the taskbar/window icon and notification-area icon in sync.
            self.window_icon = ImageTk.PhotoImage(image, master=self.root)
            self.root.iconphoto(True, self.window_icon)
            self.tray.icon = image
            self._tray_appearance = appearance
        self.tray.title = (' | '.join(f'{s.name}: {s.percent}%' if s.percent is not None else f'{s.name}: 未读取'
                                    for s in self.states) or 'DeviceViewer · 等待设备')[:127]
        self.tray.menu = self.tray_menu()
        self.tray.update_menu()

    def hide(self):
        if self.tray_ready:
            self.root.withdraw()
        else:
            self.root.iconify()

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def quit(self):
        self.closed = True
        self.tray.stop()
        self.root.destroy()

    def settings(self):
        if getattr(self, 'settings_window', None) is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title('设置')
        win.geometry(f'{self.px(540)}x{self.px(620)}')
        win.resizable(False, False)
        win.configure(bg=CARD)
        self.label(win, '电量提醒与托盘', 16, bold=True).pack(pady=(20, 12))
        alerts = tk.BooleanVar(value=self.config['alerts'])
        try:
            startup_enabled = startup.is_enabled()
        except OSError as exc:
            win.destroy()
            messagebox.showerror('无法读取开机启动设置', str(exc), parent=self.root)
            return
        autostart = tk.BooleanVar(value=startup_enabled)
        interval = tk.StringVar(value=str(self.config['interval']))
        threshold = tk.StringVar(value=str(self.config['threshold']))
        for text, var in [('开机自启动（登录后在托盘运行）', autostart), ('开启低电量提醒', alerts)]:
            tk.Checkbutton(win, text=text, variable=var, bg=CARD, fg=FG, selectcolor=BG,
                           activebackground=CARD, activeforeground=FG, font=('Microsoft YaHei UI', 11)).pack(anchor='w', padx=32, pady=6)
        threshold_row = tk.Frame(win, bg=CARD)
        threshold_row.pack(fill='x', padx=32, pady=(6, 0))
        self.label(threshold_row, '电量低于以下百分比时提醒', 10).pack(side='left')
        ttk.Combobox(threshold_row, textvariable=threshold, values=THRESHOLDS, state='readonly',
                     width=5, font=('Microsoft YaHei UI', 10)).pack(side='right')
        row = tk.Frame(win, bg=CARD)
        row.pack(fill='x', padx=32, pady=12)
        self.label(row, '刷新间隔（10–300 秒）', 10).pack(side='left')
        tk.Spinbox(row, from_=10, to=300, textvariable=interval, width=5,
                   font=('Microsoft YaHei UI', 10)).pack(side='right')
        tray_row = tk.Frame(win, bg=CARD)
        tray_row.pack(fill='x', padx=32, pady=(0, 12))
        self.label(tray_row, '托盘数字显示', 10).pack(side='left')
        snapshot = list(self.states)
        by_key = {s.key: s for s in snapshot}
        keys = [s.key for s in snapshot]
        choices = [None] + keys
        tray_choice = ttk.Combobox(tray_row, state='readonly', width=24, font=('Microsoft YaHei UI', 10))
        tray_choice['values'] = ['跟随列表第一个设备（默认）'] + [s.name for s in snapshot]
        chosen_key = self.config['tray_device']
        tray_choice.current(choices.index(chosen_key) if chosen_key in choices else 0)
        tray_choice.pack(side='right')
        self.label(win, '设备显示顺序', 11, bold=True).pack(anchor='w', padx=32, pady=(6, 4))
        self.label(win, '选中设备后上移或下移，排序会保存并同步到主界面。', 9, MUTED).pack(anchor='w', padx=32)
        list_row = tk.Frame(win, bg=CARD)
        list_row.pack(fill='x', padx=32, pady=10)
        device_list = tk.Listbox(list_row, height=4, bg=BG, fg=FG, selectbackground='#34435f',
                                selectforeground=FG, exportselection=False, relief='flat',
                                font=('Microsoft YaHei UI', 11), activestyle='none')
        device_list.pack(side='left', fill='both', expand=True)
        controls = tk.Frame(list_row, bg=CARD)
        controls.pack(side='right', padx=(10, 0))
        def fill_list(index=0):
            device_list.delete(0, 'end')
            for i, key in enumerate(keys):
                device_list.insert('end', f'{i+1}.  {by_key[key].name}')
            if keys:
                device_list.selection_set(index)
                device_list.see(index)
        def move(offset):
            selection = device_list.curselection()
            if not selection:
                return
            source = selection[0]
            target = source + offset
            if 0 <= target < len(keys):
                keys[source], keys[target] = keys[target], keys[source]
                fill_list(target)
        self.button(controls, '↑ 上移', lambda: move(-1)).pack(fill='x', pady=(0, 6))
        self.button(controls, '↓ 下移', lambda: move(1)).pack(fill='x')
        fill_list()
        self.label(win, '右键托盘也可切换设备；点击窗口 × 后仍在托盘显示电量。',
                   9, MUTED, wraplength=476, justify='left').pack(anchor='w', padx=32, pady=(0, 8))
        def save():
            try:
                seconds = int(interval.get())
                if not 10 <= seconds <= 300:
                    raise ValueError()
            except ValueError:
                messagebox.showerror('间隔无效', '请输入 10 到 300 之间的整数。', parent=win)
                return
            old_config = dict(self.config)
            old_threshold = self.config['threshold']
            old_alerts = self.config['alerts']
            # Preserve the relative order of unplugged devices after those being edited.
            order = keys + [k for k in self.config['device_order'] if k not in keys]
            self.config.update(interval=seconds, alerts=alerts.get(),
                               threshold=int(threshold.get()), device_order=order,
                               tray_device=choices[tray_choice.current()])
            try:
                previous_startup = startup.read_registration()
                # Apply only an explicit change. Merely saving unrelated settings
                # must not remove another installation's startup registration.
                startup_changed = autostart.get() != startup_enabled
                if startup_changed:
                    startup.set_enabled(autostart.get())
            except OSError as exc:
                self.config = old_config
                messagebox.showerror('开机启动设置失败', str(exc), parent=win)
                return
            try:
                self.save_config()
            except OSError as exc:
                self.config = old_config
                if startup_changed:
                    try:
                        startup.write_registration(previous_startup)
                    except OSError as rollback_error:
                        messagebox.showerror('保存失败', f'{exc}\n开机启动恢复失败：{rollback_error}', parent=win)
                        return
                messagebox.showerror('保存失败', str(exc), parent=win)
                return
            if old_threshold != self.config['threshold'] or old_alerts != self.config['alerts']:
                self.alerted.clear()
            self.states = ordered_devices(self.states, order)
            self.render()
            self.update_tray()
            self.next_scan = 0
            win.destroy()
        self.button(win, '保存设置', save, True).pack(pady=(6, 14))
        self.scale_widgets(win)

    def diagnostics(self):
        win = tk.Toplevel(self.root)
        win.title('设备与诊断')
        win.geometry(f'{self.px(720)}x{self.px(470)}')
        win.configure(bg=CARD)
        self.label(win, '已发现的 USB HID 设备', 16, bold=True).pack(anchor='w', padx=20, pady=16)
        self.label(win, '兼容性按型号和协议决定。列出设备不代表已支持其电量查询。', 10, MUTED).pack(anchor='w', padx=20)
        text = tk.Text(win, bg=BG, fg=FG, font=('Consolas', 10), relief='flat', wrap='word')
        text.pack(fill='both', expand=True, padx=20, pady=16)
        seen = set()
        for d in self.inventory:
            name = d.get('product_string') or '未命名 HID 设备'
            key = (d['vendor_id'], d['product_id'], name)
            if key in seen:
                continue
            seen.add(key)
            text.insert('end', f'{name}\nVID {d["vendor_id"]:04X} · PID {d["product_id"]:04X}\n\n')
        if not seen:
            text.insert('end', '未发现 HID 设备。请在正常 Windows 桌面环境运行并插入接收器。')
        text.configure(state='disabled')
        def export():
            path = filedialog.asksaveasfilename(parent=win, defaultextension='.json', initialfile='DeviceViewer-diagnostics.json',
                                              filetypes=[('JSON', '*.json')])
            if not path:
                return
            # Paths and serials are omitted from exports; only model and protocol details are needed.
            data = {'devices': [{k: v for k, v in asdict(s).items() if k != 'key'} for s in self.states],
                    'hid': [{k: v for k, v in d.items() if k not in ('path', 'serial_number')} for d in self.inventory]}
            try:
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror('导出失败', str(exc), parent=win)
        self.button(win, '导出诊断信息', export).pack(pady=(0, 16))
        self.scale_widgets(win)

    def run(self):
        self.root.mainloop()
