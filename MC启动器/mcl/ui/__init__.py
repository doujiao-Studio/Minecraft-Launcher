"""UI 包：基于 Tkinter/ttk 的桌面界面。"""
import traceback

import tkinter as tk

from .. import paths
from .app import MainWindow


def run():
    info = paths.ensure_layout()  # 首次运行：自动创建 NCLData / .minecraft
    root = tk.Tk()
    win = MainWindow(root)
    if info["first_run"]:
        root.after(600, lambda: _first_run_guide(win, info))
    root.mainloop()


def _first_run_guide(win: MainWindow, info: dict) -> None:
    """首次运行：静默打好初始化标记，仅在状态栏提示目录位置并跳到下载中心。

    不弹任何对话框——用户双击 exe 就该直接开始用。
    """
    from .. import utils
    log = utils.get_logger("firstrun")
    try:
        paths.mark_initialized()
        win.select_tab(2)  # 下载中心
        try:
            win.status.configure(
                text=f"数据目录: {info['root']}  |  游戏目录: {info['minecraft']}"
                     "   （首次运行已自动创建）")
        except Exception:
            pass
        log.info("首次运行: root=%s, mc=%s", info["root"], info["minecraft"])
    except Exception:
        log.warning("首次运行引导失败:\n%s", traceback.format_exc())
