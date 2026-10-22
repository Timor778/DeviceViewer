"""Developer diagnostic: read-only HID++ ROOT queries."""
import hid
for d in hid.enumerate(0x046d):
    if d['usage_page'] != 0xff00:
        continue
    h = hid.device()
    try:
        h.open_path(d['path'])
        print('collection', d['usage'])
        for slot in (1, 0xff):
            for rid, size in ((0x10, 7), (0x11, 20)):
                packet = bytes([rid, slot, 0, 0x0a, 0x10, 0x04, 0]).ljust(size, b'\0')
                print('send', packet.hex(), 'written', h.write(packet))
                for _ in range(3):
                    print('reply', bytes(h.read(64, 200)).hex())
    except OSError as e:
        print(e)
    finally:
        h.close()
