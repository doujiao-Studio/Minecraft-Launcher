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
from . import anim, bus, navbar, theme
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
        root.title("NCL 启动器")

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
        # 给所有按钮挂上点击动画
        anim.bind_click_all(root)

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
            h2 = fw(None, "NCL 启动器")
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

    # ---------- 自绘标题栏（Canvas 渐变） ----------
    _BAR_H = 60
    _BTN_W = 48

    def _build_titlebar(self):
        bar = tk.Canvas(self.root, height=self._BAR_H, highlightthickness=0, bd=0,
                        bg=theme.PRIMARY, cursor="arrow")
        bar.pack(fill="x")
        self._bar = bar
        self._grad_items = []
        bar.bind("<Configure>", lambda e: self._paint_titlebar())
        bar.bind("<Button-1>", self._start_move)
        bar.bind("<Double-Button-1>", self._on_bar_dblclick)

        # 品牌区：图标 + 标题 + 副标题（直接画在渐变上，原生通透）
        x = 16
        if self._icon:
            bar.create_image(x, self._BAR_H // 2, image=self._icon, anchor="w",
                             tags="brand")
            x += 42
        bar.create_text(x, 22, text="NCL 启动器", anchor="w", fill="#ffffff",
                        font=theme.FONT_TITLE, tags="brand")
        bar.create_text(x, 44, text="我的世界 · 启动 / 服务器 / 内网穿透 一站式工具",
                        anchor="w", fill="#dfe4ff", font=theme.FONT_SMALL, tags="brand")
        bar.tag_bind("brand", "<Button-1>", self._start_move)
        bar.tag_bind("brand", "<Double-Button-1>", self._on_bar_dblclick)

        # 右侧窗口按钮：矩形热区 + 符号，悬停高亮
        self._win_btns = []  # (rect_id, text_id, kind)
        for kind, symbol, tip in (("min", "—", "最小化"),
                                  ("max", "▢", "最大化 / 还原"),
                                  ("close", "✕", "关闭")):
            r = bar.create_rectangle(0, 0, 0, 0, fill="", outline="",
                                     tags=("winbtn", f"btn_{kind}"))
            t = bar.create_text(0, 0, text=symbol, fill="#ffffff",
                                font=("Segoe UI Symbol", 13),
                                tags=("winbtn", f"btn_{kind}"))
            bar.tag_bind(f"btn_{kind}", "<Enter>",
                         lambda e, k=kind: self._btn_hover(k, True))
            bar.tag_bind(f"btn_{kind}", "<Leave>",
                         lambda e, k=kind: self._btn_hover(k, False))
            bar.tag_bind(f"btn_{kind}", "<ButtonPress-1>",
                         lambda e, k=kind: self._btn_click(k))
            self._win_btns.append((r, t, kind))

    def _paint_titlebar(self):
        """宽度变化时重绘水平渐变，并重新布局右侧按钮。"""
        bar = self._bar
        w = max(bar.winfo_width(), 2)
        h = self._BAR_H
        bar.delete("grad")
        steps = max(w // 3, 1)
        sw = w / steps
        for i in range(steps):
            color = theme.lerp_color(theme.GRADIENT_FROM, theme.GRADIENT_TO,
                                     i / max(steps - 1, 1))
            bar.create_rectangle(int(i * sw), 0, int((i + 1) * sw) + 1, h,
                                 fill=color, outline=color, tags="grad")
        bar.tag_lower("grad")
        # 右侧按钮布局
        for i, (r, t, _kind) in enumerate(self._win_btns):
            x1 = w - (len(self._win_btns) - i) * self._BTN_W
            bar.coords(r, x1, 0, x1 + self._BTN_W, h)
            bar.coords(t, x1 + self._BTN_W / 2, h / 2)

    def _btn_hover(self, kind: str, on: bool):
        for r, _t, k in self._win_btns:
            if k != kind:
                continue
            if not on:
                self._bar.itemconfigure(r, fill="", stipple="")
            elif kind == "close":
                self._bar.itemconfigure(r, fill=theme.DANGER, stipple="")
            else:
                # 白色 25% 点刻 = 轻量半透明悬停感
                self._bar.itemconfigure(r, fill="#ffffff", stipple="gray25")

    def _btn_click(self, kind: str):
        {"min": self._minimize, "max": self._toggle_max,
         "close": self._on_close}[kind]()

    def _on_bar_dblclick(self, e):
        if self._over_winbtn():
            return
        self._toggle_max()

    def _over_winbtn(self) -> bool:
        """当前指针是否落在窗口按钮上（避免按钮点击触发拖动/双击最大化）。"""
        try:
            cur = self._bar.find_withtag("current")
            return bool(cur) and "winbtn" in self._bar.gettags(cur[0])
        except Exception:
            return False

    # ---------- 内容区 ----------
    def _build_notebook(self):
        nb = ttk.Notebook(self.root)
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
        # 顶部导航按钮（选中态颜色渐变 + 指示条滑动）—— 必须先于 notebook pack，
        # 否则会被 expand 的 notebook 挤出可视区
        self._nav = navbar.NavTabs(self.root, nb)
        self._nav.pack(fill="x", padx=14, pady=(8, 4))
        nb.pack(fill="both", expand=True, padx=14)

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
        grip = tk.Frame(self.root, bg="#d9dee9", cursor="bottom_right_corner", width=18, height=18)
        grip.place(relx=1.0, rely=1.0, anchor="se")
        grip.bind("<ButtonPress-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._do_resize)

    # ---------- 窗口行为 ----------
    def _start_move(self, e):
        """系统原生拖动：发 WM_NCLBUTTONDOWN + HTCAPTION 让系统接管移动，
        避免无边框窗口用 geometry 手动移动导致整窗重绘、闪烁花屏。"""
        if self._over_winbtn():
            return
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

    def select_tab(self, index: int):
        """切到指定页签（同步自绘导航条）。"""
        try:
            self._nav.select(index)
        except Exception:
            try:
                self._nb.select(index)
            except Exception:
                pass

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
