"""截图：仅验证导航栏渲染（不依赖网络）。"""
from __future__ import annotations
import ctypes, os, sys, time, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import tkinter as tk  # noqa: E402
import tkinter.ttk as ttk  # noqa: E402
from PIL import ImageGrab  # noqa: E402
from mcl.ui.app import MainWindow  # noqa: E402
from mcl.ui import bus  # noqa: E402
from mcl.ui.download_center_tab import ModDetailWindow  # noqa: E402

OUT = os.path.join(ROOT, ".workbuddy", "screens")
os.makedirs(OUT, exist_ok=True)


def window_box(root):
    try:
        user32 = ctypes.windll.user32
        wt = ctypes.wintypes
        results = []
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(hwnd, _l):
            buf = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(hwnd, buf, 64)
            if buf.value == "NCL 启动器" and user32.IsWindowVisible(hwnd):
                r = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                results.append((r.left, r.top, r.right, r.bottom))
            return True
        user32.EnumWindows(proto(cb), 0)
        if results:
            return max(results, key=lambda b: (b[2]-b[0])*(b[3]-b[1]))
    except Exception:
        pass
    return None


def shot(root, name, title="NCL 启动器"):
    """PrintWindow 直接抓指定标题窗口的内容（不依赖窗口是否被遮挡）。"""
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        print("no window for", name)
        return
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT
    # BITMAPINFOHEADER + 读取像素
    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]
    bmi = BMIH()
    ctypes.memset(ctypes.byref(bmi), 0, ctypes.sizeof(bmi))
    bmi.biSize = ctypes.sizeof(BMIH)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0  # BI_RGB
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    from PIL import Image
    img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
    img.convert("RGB").save(os.path.join(OUT, name))
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    print("saved", name, ok, (w, h))


def pump(root, ms):
    end = time.time() + ms/1000
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def main():
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda e, v, t: errors.append(
        traceback.format_exception(e, v, t)[-1])
    bus.init(root)
    app = MainWindow(root)
    pump(root, 600)

    # L1 nav
    app._nav.select(2)
    pump(root, 400)
    shot(root, "shot_l1.png")

    # L2 nav: download center's inner notebook
    inner_nb = None
    for w in app.download.winfo_children():
        if isinstance(w, ttk.Notebook):
            inner_nb = w
    print("inner_nb found:", inner_nb is not None)
    if inner_nb:
        app.download.nav.select(1)  # 模组
        pump(root, 500)
        shot(root, "shot_l2.png")
        # dump children geometry of download tab to locate gray frames
        for ch in app.download.winfo_children():
            try:
                print("L2 child:", ch.winfo_class(), ch.winfo_x(), ch.winfo_y(),
                      ch.winfo_width(), ch.winfo_height(),
                      getattr(ch, "cget", lambda: "")("bg") if hasattr(ch, "cget") else "")
            except Exception as e:
                print("  err", e)

    # L3 nav: detail window directly
    if inner_nb:
        pane = inner_nb.nametowidget(inner_nb.tabs()[1])
        try:
            dw = ModDetailWindow(pane, {"title": "示例模组", "slug": "demo",
                                        "project_id": "x", "icon": "",
                                        "author": "tester", "downloads": 1234,
                                        "description": "测试简介"},
                                 "mod", "1.21.1", "", None, pane.loader)
            pump(root, 800)
            shot(root, "shot_l3.png", title="示例模组")
        except Exception as e:
            print("detail err:", repr(e))
            traceback.print_exc()

    root.destroy()
    if errors:
        print("UI ERRORS:", errors[:5])
        return 1
    print("SHOT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
