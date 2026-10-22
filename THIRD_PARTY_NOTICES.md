# Third-party dependencies and protocol references

DeviceViewer's original application code is licensed under MIT. Dependencies retain their own licenses:

| Dependency | License | Project |
| --- | --- | --- |
| hidapi (Python bindings) | BSD-3-Clause | https://github.com/trezor/cython-hidapi |
| HIDAPI native library | BSD-3-Clause / GPL-3.0 / HIDAPI license, alternative licenses | https://github.com/libusb/hidapi |
| pystray | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| Pillow | MIT-CMU | https://github.com/python-pillow/Pillow |
| six | MIT | https://github.com/benjaminp/six |
| Python / Tk | PSF / Tcl-Tk licenses | https://www.python.org/ / https://www.tcl.tk/ |
| PyInstaller (build tool and bootloader) | GPL-2.0-or-later with bootloader exception | https://pyinstaller.org/ |

Packaged builds retain dependency metadata and bundled license files. They are folder-based builds: Python modules and shared libraries remain separately replaceable. Source is available from the linked upstream projects; build instructions are in README.md.

The application queries battery status using independently implemented packet encoding and decoding based on publicly described protocols. It does not include the source of HeadsetControl or Solaar:

- https://github.com/Sapd/HeadsetControl/blob/master/lib/devices/protocols/sony_inzone_protocol.hpp
- https://github.com/pwr-Solaar/Solaar/blob/master/lib/logitech_receiver/hidpp20.py

Logitech, LIGHTSPEED, Sony and INZONE are trademarks of their respective owners. DeviceViewer is an independent project and is not affiliated with or endorsed by these companies.
