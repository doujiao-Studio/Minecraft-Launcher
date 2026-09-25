"""主窗口：无边框现代应用样式。

- 自绘标题栏（品牌区）：图标 + 标题 + 最小化 / 最大化 / 关闭
- 标题栏拖动窗口、双击最大化、右下角缩放手柄
- 全局主题 + 六个标签页 + 状态栏
- 普通顶层窗口自带任务栏；持续守护移除系统标题栏(对抗 Tk 维护的 WS_CAPTION)，实现无边框且任务栏可见
"""
from __future__ import annotations
import ctypes
import os
import sys
import tkinter as tk
from tkinter import ttk

from .. import config, paths
from . import bus, theme
from .download_center_tab import DownloadCenterTab
from .launcher_tab import LauncherTab
from .server_tab import ServerTab
from .settings_tab import SettingsTab
from .tunnel_tab import TunnelTab
from .version_tab import VersionTab

_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WS_SYSMENU = 0x00080000
_WS_MINIMIZEBOX = 0x00020000
_WS_MAXIMIZEBOX = 0x00010000
_WS_BORDER = 0x00800000

def _asset(name: str) -> str:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", ".")
        return os.path.join(base, "assets", name)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "assets", name)

class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        bus.init(root)
        theme.apply(root)

        # 普通顶层窗口：任务栏天然显示(无 TOOLWINDOW)；不用 overrideredirect
        root.configure(bg=theme.BG)
        root.geometry("980x780")
        root.minsize(860, 660)
        root.title("MCL·神启动器")

        try:
            icon = tk.PhotoImage(file=_asset("icon_small.png"))
            root.iconphoto(True, icon)
            self._icon = icon
        except Exception:
            self._icon = None

        self._maxed = False
        self._restore_geom = None
        self._drag = None
        self._resize = None

        self._build_titlebar()
        self._build_notebook()
        self._build_status()
        self._build_resize_grip()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._minimizing = False
        # 窗口映射后隐藏系统标题栏；并启动持续守护对抗 Tk 的样式覆盖
        root.after(150, lambda: self._hide_caption_once(0))
        root.after(700, self._keep_no_caption)

    def _setup_win32(self):
        """正确设置 ctypes 参数类型(64 位句柄不截断)。"""
        import ctypes.wintypes as wt
        u = ctypes.windll.user32
        u.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
        u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        return u

    # ---------- 无边框(隐藏系统标题栏，保留任务栏) ----------
    def _apply_no_caption(self, u, hwnd):
        style = u.GetWindowLongPtrW(hwnd, _GWL_STYLE)
        if not (style & _WS_CAPTION):
            return True  # 已无标题栏
        style &= ~(_WS_CAPTION | _WS_THICKFRAME | _WS_SYSMENU |
                   _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX)
        style |= _WS_BORDER
        u.SetWindowLongPtrW(hwnd, _GWL_STYLE, style)
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                       0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        aft = u.GetWindowLongPtrW(hwnd, _GWL_STYLE)
        return not (aft & _WS_CAPTION)

    def _hide_caption_once(self, attempt: int = 0):
        try:
            u = self._setup_win32()
            hwnd = self._find_real_hwnd()
            if not hwnd or hwnd <= 0:
                if attempt < 40:
                    self.root.after(120, lambda: self._hide_caption_once(attempt + 1))
                return
            if not self._apply_no_caption(u, hwnd) and attempt < 40:
                self.root.after(150, lambda: self._hide_caption_once(attempt + 1))
        except Exception:
            if attempt < 40:
                self.root.after(150, lambda: self._hide_caption_once(attempt + 1))

    def _find_real_hwnd(self):
        """PyInstaller 环境下 winfo_id() 可能与真实可见窗口不一致，
        用 FindWindowW 按标题定位真实顶层窗口；失败回退 winfo_id()。"""
        hwnd = self.root.winfo_id()
        try:
            import ctypes.wintypes as wt
            fw = ctypes.windll.user32.FindWindowW
            fw.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
            fw.restype = wt.HWND
            h2 = fw(None, "MCL·神启动器")
            if h2:
                hwnd = h2
        except Exception:
            pass
        return hwnd

    def _apply_round_corners(self, hwnd):
        """DWM 圆角(Windows 11)，边角圆滑；Win10 不支持则静默忽略。"""
        try:
            import ctypes.wintypes as wt
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute.argtypes = [wt.HWND, ctypes.c_uint,
                                                  ctypes.c_void_p, ctypes.c_uint]
            pref = ctypes.c_int(DWMWCP_ROUND)
            dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                      ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass

    def _keep_no_caption(self):
        """持续守护：移除系统标题栏 + 保持圆角，直到窗口关闭。"""
        try:
            u = self._setup_win32()
            hwnd = self._find_real_hwnd()
            if hwnd and hwnd > 0:
                self._apply_no_caption(u, hwnd)
                self._apply_round_corners(hwnd)
        except Exception:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(700, self._keep_no_caption)
        except Exception:
            pass

    # ---------- 自绘标题栏 ----------
    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=theme.PRIMARY, height=58)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        bar.bind("<Button-1>", self._start_move)
        bar.bind("<B1-Motion>", self._do_move)
        bar.bind("<Double-Button-1>", lambda e: self._toggle_max())

        left = tk.Frame(bar, bg=theme.PRIMARY)
        left.pack(side="left", padx=(16, 0))
        for w in (left, bar):
            w.bind("<Button-1>", self._start_move, add="+")
            w.bind("<B1-Motion>", self._do_move, add="+")
        if self._icon:
            tk.Label(left, image=self._icon, bg=theme.PRIMARY).pack(side="left")
        title = tk.Frame(left, bg=theme.PRIMARY)
        title.pack(side="left", padx=(10, 0))
        tk.Label(title, text="MCL · 神启动器", bg=theme.PRIMARY, fg="#ffffff",
                 font=theme.FONT_TITLE).pack(anchor="w")
        tk.Label(title, text="我的世界 · 启动 / 服务器 / 内网穿透 一站式工具",
                 bg=theme.PRIMARY, fg="#dbe3ff", font=theme.FONT_SMALL).pack(anchor="w")
        title.bind("<Button-1>", self._start_move, add="+")
        title.bind("<B1-Motion>", self._do_move, add="+")

        right = tk.Frame(bar, bg=theme.PRIMARY)
        right.pack(side="right", padx=(0, 6))
        self._add_win_btn(right, "—", "最小化", self._minimize, hover="#4259c9")
        self._add_win_btn(right, "▢", "最大化 / 还原", self._toggle_max, hover="#4259c9")
        self._add_win_btn(right, "✕", "关闭", self._on_close, hover="#e03131")

    def _add_win_btn(self, parent, text, tip, action, hover):
        b = tk.Label(parent, text=text, bg=theme.PRIMARY, fg="#ffffff",
                     font=("Segoe UI Symbol", 14), padx=13, pady=14, cursor="hand2")
        b.pack(side="left")
        b.bind("<Enter>", lambda e: b.configure(bg=hover))
        b.bind("<Leave>", lambda e: b.configure(bg=theme.PRIMARY))
        b.bind("<ButtonPress-1>", lambda e: action())
        widgets_tooltip(b, tip)
        return b

    # ---------- 内容区 ----------
    def _build_notebook(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        self.launcher = LauncherTab(nb)
        self.versions = VersionTab(nb)
        self.download = DownloadCenterTab(nb)
        self.server = ServerTab(nb)
        self.tunnel = TunnelTab(nb)
        self.settings = SettingsTab(nb)
        nb.add(self.launcher, text="  启动器  ")
        nb.add(self.versions, text="  版本管理  ")
        nb.add(self.download, text="  下载中心  ")
        nb.add(self.server, text="  服务器  ")
        nb.add(self.tunnel, text="  内网穿透  ")
        nb.add(self.settings, text="  设置  ")
        last = config.get("last_tab", "launcher")
        index = {"launcher": 0, "version": 1, "server": 3,
                 "tunnel": 4, "settings": 5}.get(last, 0)
        nb.select(index)
        nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab(nb, nb.index("current")))
        self._nb = nb

    def _build_status(self):
        bar = tk.Frame(self.root, bg="#ffffff", height=30, highlightbackground=theme.BORDER,
                       highlightthickness=1)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status = tk.Label(bar, text=f"数据目录: {paths.base_dir()}", anchor="w",
                               bg="#ffffff", fg=theme.MUTED, font=theme.FONT_SMALL)
        self.status.pack(fill="x", side="left", padx=14)
        tk.Label(bar, text="纯 Python 实现 · 零依赖", anchor="e",
                 bg="#ffffff", fg=theme.MUTED, font=theme.FONT_SMALL).pack(side="right", padx=14)

    def _build_resize_grip(self):
        grip = tk.Frame(self.root, bg="#e3e6ee", cursor="bottom_right_corner", width=18, height=18)
        grip.place(relx=1.0, rely=1.0, anchor="se")
        grip.bind("<ButtonPress-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._do_resize)

    # ---------- 窗口行为 ----------
    def _start_move(self, e):
        """系统原生拖动：发 WM_NCLBUTTONDOWN + HTCAPTION 让系统接管移动，
        避免无边框窗口用 geometry 手动移动导致整窗重绘、闪烁花屏。"""
        try:
            import ctypes.wintypes as wt
            user32 = ctypes.windll.user32
            user32.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_uint,
                                            ctypes.c_long]
            hwnd = self._find_real_hwnd()
            if hwnd and hwnd > 0:
                user32.ReleaseCapture()
                lp = (e.x_root & 0xffff) | ((e.y_root & 0xffff) << 16)
                user32.PostMessageW(hwnd, 0x00A1, 2, lp)  # WM_NCLBUTTONDOWN, HTCAPTION
        except Exception:
            pass

    def _do_move(self, e):
        pass  # 系统原生拖动接管后无需手动移动

    def _work_area(self):
        """工作区(屏幕去除任务栏后的区域)。"""
        try:
            import ctypes.wintypes as wt
            u = ctypes.windll.user32
            u.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint,
                                                ctypes.c_void_p, ctypes.c_uint]
            r = wt.RECT()
            u.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
            return r.right - r.left, r.bottom - r.top, r.left, r.top
        except Exception:
            return (self.root.winfo_screenwidth(), self.root.winfo_screenheight(), 0, 0)

    def _toggle_max(self, _e=None):
        if self._maxed:
            if self._restore_geom:
                self.root.geometry(self._restore_geom)
            self._maxed = False
        else:
            self._restore_geom = self.root.geometry()
            w, h, x, y = self._work_area()
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self._maxed = True

    def _minimize(self):
        """普通顶层窗口最小化：原生任务栏，iconify 后可从任务栏还原。"""
        try:
            self.root.iconify()
        except Exception:
            pass

    def _start_resize(self, e):
        self._resize = (e.x_root, e.y_root)
        self._geom = (self.root.winfo_width(), self.root.winfo_height())

    def _do_resize(self, e):
        if self._resize:
            dx = e.x_root - self._resize[0]
            dy = e.y_root - self._resize[1]
            w = max(self._geom[0] + dx, self.root.minsize()[0])
            h = max(self._geom[1] + dy, self.root.minsize()[1])
            self.root.geometry(f"{w}x{h}")

    def _on_tab(self, nb, idx):
        name = {0: "launcher", 1: "version", 2: "download", 3: "server",
                4: "tunnel", 5: "settings"}.get(idx, "launcher")
        config.set("last_tab", name)

    def _on_close(self):
        try:
            self.server.stop_server()
        except Exception:
            pass
        self.root.destroy()

def widgets_tooltip(widget, text):
    try:
        from .widgets import ToolTip
        ToolTip(widget, text, delay=450)
    except Exception:
        pass
