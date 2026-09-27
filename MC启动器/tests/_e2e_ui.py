"""端到端 UI 视觉验证（单进程驱动真实界面 + 截图）。

流程：启动完整主窗口 -> 切到下载中心（抓转场动画帧）-> 模组子页 ->
真实搜索 sodium（Modrinth 在线）-> 等待卡片与图标渲染 -> 截图。
"""
from __future__ import annotations
import ctypes
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = os.path.join(ROOT, "NCLData")   # 用真实数据目录，展示已装模组环境

try:  # 让截图与窗口坐标都是物理像素
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import tkinter as tk  # noqa: E402
import ctypes.wintypes as wt  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from mcl.ui.app import MainWindow  # noqa: E402
from mcl.ui import bus  # noqa: E402

OUT = os.path.join(ROOT, ".workbuddy", "screens")
os.makedirs(OUT, exist_ok=True)


def window_box(root):
    """找标题为「NCL 启动器」的最大可见窗口（跳过 tooltip 等小窗）。"""
    try:
        user32 = ctypes.windll.user32
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
            return max(results, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    except Exception:
        pass
    return None


def shot(root, name):
    box = window_box(root)
    if box:
        # 启动器窗口可能被其他应用遮挡：先置顶再抓屏
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "NCL 启动器")
            if hwnd:
                user32.SetForegroundWindow(hwnd)
                time.sleep(0.35)
        except Exception:
            pass
        ImageGrab.grab(bbox=box).save(os.path.join(OUT, name))
        print("saved", name, box)


def pump(root, ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def main() -> int:
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda e, v, t: errors.append(
        traceback.format_exception(e, v, t)[-1])
    bus.init(root)
    app = MainWindow(root)
    pump(root, 600)

    # 1) 切到下载中心（一级导航按钮动画）
    app._nav.select(2)
    pump(root, 400)
    shot(root, "e2e_l1_nav.png")

    # 2) 二级导航：切到「模组」子页
    mod_pane = None
    import tkinter.ttk as ttk
    inner_nb = None
    for w in app.download.winfo_children():
        if isinstance(w, ttk.Notebook):
            inner_nb = w
    assert inner_nb is not None, "未找到下载中心子页签"
    app.download.nav.select(1)  # 模组
    pump(root, 500)
    shot(root, "e2e_l2_nav.png")
    mod_pane = inner_nb.nametowidget(inner_nb.tabs()[1])

    # 3) 真实搜索（Modrinth 在线）
    mod_pane.query_var.set("sodium")
    mod_pane.do_search()
    deadline = time.time() + 25
    while time.time() < deadline:
        pump(root, 200)
        if mod_pane.grid.cards:
            break
    # 再等图标下载渲染
    pump(root, 6000)
    shot(root, "e2e_mod_results.png")
    n = len(mod_pane.grid.cards)
    print(f"cards: {n}")
    print("status:", mod_pane.status_var.get())

    # 4) 选中第一张卡片打开详情页
    if mod_pane.grid.cards:
        mod_pane.grid.cards[0]._click()
        pump(root, 2500)
        shot(root, "e2e_detail.png")

    root.destroy()
    if errors:
        print("UI ERRORS:")
        for e in errors[:5]:
            print(" ", e)
        return 1
    print("E2E OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
