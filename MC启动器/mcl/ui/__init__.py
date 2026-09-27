"""UI 包：基于 Tkinter/ttk 的桌面界面。"""
import traceback

import tkinter as tk
from tkinter import messagebox

from .. import paths
from .app import MainWindow


def run():
    info = paths.ensure_layout()  # 首次运行：自动创建 NCLData / .minecraft
    root = tk.Tk()
    win = MainWindow(root)
    if info["first_run"]:
        root.after(600, lambda: _first_run_guide(root, win, info))
    root.mainloop()


def _first_run_guide(root, win: MainWindow, info: dict) -> None:
    """首次运行引导：告知数据目录位置，并引导去下载游戏版本。"""
    from .. import utils
    log = utils.get_logger("firstrun")
    try:
        paths.mark_initialized()
        win.select_tab(2)  # 下载中心
        try:
            win.status.configure(
                text=f"首次运行已创建数据目录: {info['root']}  |  游戏目录: {info['minecraft']}")
        except Exception:
            pass
        log.info("首次运行引导: root=%s, mc=%s", info["root"], info["minecraft"])
        messagebox.showinfo(
            "欢迎使用 NCL 启动器",
            "已自动创建启动器文件夹：\n\n"
            f"数据目录：{info['root']}\n"
            f"游戏目录：{info['minecraft']}\n\n"
            "接下来请在「下载中心 → 游戏本体」里选一个版本下载，\n"
            "下载完成后回到「启动器」页即可启动游戏。\n\n"
            "（正版玩家可先点「正版登录 (Microsoft)」登录）",
            parent=root)
    except Exception:
        log.warning("首次运行引导失败:\n%s", traceback.format_exc())
