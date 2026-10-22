import ctypes
import os
from PIL import Image, ImageDraw, ImageFont


def enable_dpi_awareness():
    """Call before Tk creates any HWND, including when running from Python."""
    if os.name != 'nt':
        return
    try:
        # The executable manifest also sets this. Access denied means it is already set.
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass


def window_dpi(root):
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        return ctypes.windll.user32.GetDpiForWindow(hwnd) or 96
    except (AttributeError, OSError):
        return round(root.winfo_fpixels('1i'))


def battery_icon(percent, low=False):
    """Render large glyphs, with no percent suffix, legible at notification-area sizes."""
    image = Image.new('RGBA', (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 127, 127), radius=23, fill='#202938')
    text = str(percent) if percent is not None else '–'
    font_path = os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts', 'segoeuib.ttf')
    size = 105
    while True:
        try:
            font = ImageFont.truetype(font_path, size)
        except OSError:
            font = ImageFont.load_default(size=size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2]-box[0] <= 120 or size <= 30:
            break
        size -= 1
    x = (128-(box[2]-box[0]))/2-box[0]
    y = (128-(box[3]-box[1]))/2-box[1]
    draw.text((x, y), text, fill='#ffbd70' if low else '#ffffff', font=font)
    return image
