# DeviceViewer · 外设电量

Windows 本地桌面软件，统一显示无线鼠标、耳机的真实电量。无需打开品牌驱动界面，无需管理员权限。

## 下载与安装

在 GitHub Releases 中下载 Windows 压缩包，解压后运行 `DeviceViewer.exe`。请保留整个文件夹。软件支持 Windows 10 / 11 x64。

## 使用

双击 `dist/DeviceViewer/DeviceViewer.exe`，或项目中的 `start.bat`。发布给其他电脑时，请复制整个 `dist/DeviceViewer` 文件夹，不能只复制其中的 exe。

- 每 30 秒自动刷新，也可手动刷新。
- 关闭窗口后收起到系统托盘；双击托盘图标恢复，右键可刷新或退出。
- 托盘悬停可查看设备百分比。
- 托盘图标直接显示所选设备的电量数字（例如 `48`）；默认跟随设备列表的第一个设备，未知电量显示 `–`。右键托盘可切换设备。Windows 若将图标折叠在隐藏区域，可把该图标拖至右下角常驻区域。
- 设置中可上下调整设备显示顺序，排序会保存并同步到主界面。
- 低电量提醒阈值可选 10%、20%、30%、40%、50%，默认**低于 50%**提醒；等于阈值或充电中不提醒。每轮低电量状态只提醒一次，恢复至阈值或开始充电后重置。
- 设置中可调整刷新间隔、提醒开关、阈值和托盘显示设备；设置保存在 `%LOCALAPPDATA%/DeviceViewer/settings.json`。
- 设置中可勾选“开机自启动”，保存后在当前用户下次登录 Windows 时自动启动，并仅在托盘显示。默认关闭，无需管理员权限；取消勾选并保存即可关闭。启用后请保留程序所在文件夹；移动程序后需在新位置重新启用。
- 支持 Windows Per-Monitor V2 DPI 感知，字体直接按屏幕 DPI 渲染，控件与电量圆环同步缩放；切换到不同缩放比例的屏幕时主窗口自动调整。
- “设备与诊断”展示已发现型号并可导出不含序列号、设备路径的诊断信息。
- 默认不启用开机启动，不联网，不修改外设设置。自启动仅写入当前用户的 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\DeviceViewer`，不影响其他用户。

## 兼容范围

已在本机真实验证：

| 设备 | 电量接口 | 验证状态 |
| --- | --- | --- |
| Logitech PRO X 2，接收器 046D:C54D | HID++ 2.0 / 0x1004 | 已验证 |
| Sony INZONE H5，接收器 054C:0EBF | Sony HCI over HID | 已验证 |

实现罗技 HID++ `0x1004` 与 `0x1000` 电量查询及 Sony INZONE H5 适配。其他罗技型号是否可用取决于协议、接口和固件，尚未逐一验证。

**不能保证“任意 2.4G 外设”直接可用**：2.4GHz 是无线频段，各品牌的 USB 接收器并没有统一的电量协议。新增品牌需新增适配器；未知设备只枚举，不盲发报文。仅提供电压、分档电量或旧版 HID++ 的设备暂不支持百分比。

未读取时显示原因，不显示虚构电量或上次缓存。设备关机、休眠、接收器拔出或其他软件独占可能影响查询；请先开启设备并移动鼠标唤醒，必要时退出品牌软件后刷新。单次扫描通常几秒内完成，多个未响应设备会延长扫描时间。

罗技查询会清理待处理响应、轮换事务标识，并通过 FeatureSet 校验实际特性 ID；只有连续两次电量与充电状态一致才发布。支持的电量接口发生超时或响应冲突时，不切换到旧协议解释数据，避免将功能参数误显示成“15%、正在充电”。

## 开发

Python 3.11 / Windows 10、11 x64，Tkinter UI，hidapi 通信，pystray 托盘。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\build.ps1
```

命令行读取一次：`DeviceViewer.exe --diagnose diagnostics.json`。命令行诊断包含原始 HID 路径和序列号，仅供本地调试；分享时请优先用界面的脱敏导出。

实现扩展入口为 `deviceviewer/devices.py` 的 `scan()` 和 `Battery` 数据模型。电量请求在工作线程执行，UI 与托盘事件通过队列汇集到 Tk 主线程。

## 协议参考

按公开报文格式独立实现，仅实现电量读取：

- [HeadsetControl Sony INZONE H5](https://github.com/Sapd/HeadsetControl/blob/master/lib/devices/sony_inzone_h5.hpp)
- [Sony INZONE protocol](https://github.com/Sapd/HeadsetControl/blob/master/lib/devices/protocols/sony_inzone_protocol.hpp)
- [Solaar HID++ protocol implementation](https://github.com/pwr-Solaar/Solaar/blob/master/lib/logitech_receiver/hidpp20.py)

第三方依赖随发布目录附带其许可证元数据。

## 参与适配

欢迎通过 Issue 提交设备型号、USB VID/PID、固件版本和复现步骤。分享诊断信息时请使用界面的脱敏导出，不要上传原始序列号、设备路径或个人配置。新增设备适配应仅查询已知的电量协议，并为报文解析、无效响应和离线状态添加测试。

## 开源许可

本项目采用 [MIT License](LICENSE)。第三方依赖及协议参考见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
