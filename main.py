import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='DeviceViewer 外设电量')
    parser.add_argument('--diagnose', metavar='FILE', help='读取一次真实电量并保存 JSON')
    args = parser.parse_args()
    if args.diagnose:
        from deviceviewer.devices import diagnostic
        Path(args.diagnose).write_text(json.dumps(diagnostic(), ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        from deviceviewer.display import enable_dpi_awareness
        enable_dpi_awareness()
        from deviceviewer.app import App
        App().run()


if __name__ == '__main__':
    main()
