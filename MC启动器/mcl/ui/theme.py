"""全局主题：现代化、干净的配色与控件样式（基于 clam 主题深度定制）。

只定制默认样式类，现有所有控件自动获得新外观，无需逐处修改。
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

# ---- 配色板（现代 · 靛蓝渐变系）----
BG = "#eef1f7"          # 页面背景（淡蓝灰）
CARD = "#ffffff"        # 卡片/面板背景
PRIMARY = "#4a6cf7"     # 主色（靛蓝）
PRIMARY_DARK = "#3b57d9"
PRIMARY_PRESSED = "#2f46b8"
PRIMARY_LIGHT = "#e8edff"   # 主色浅底（悬停/浅选中）
GRADIENT_FROM = "#4a6cf7"   # 标题栏渐变起
GRADIENT_TO = "#7a5af8"     # 标题栏渐变止（紫）
ACCENT = "#12b76a"      # 成功绿
WARN = "#f79009"
DANGER = "#e5484d"
TEXT = "#1f2430"
MUTED = "#8a94a6"
BORDER = "#e2e7f0"
SELECT = "#dbe4ff"      # 列表选中（浅蓝）
ROW_ALT = "#f7f9fd"
INPUT_BG = "#ffffff"
DISABLED_FG = "#b7c0d8"

FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 15, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_MONO = ("Consolas", 10)


def apply(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # 全局
    style.configure(".", background=BG, foreground=TEXT, font=FONT)

    # 容器
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabelframe", background=CARD, bordercolor=BORDER,
                    relief="solid", borderwidth=1, padding=10)
    style.configure("TLabelframe.Label", background=CARD, foreground=PRIMARY,
                    font=FONT_BOLD)
    style.configure("TSeparator", background=BORDER)

    # 标签
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
    style.configure("Title.TLabel", background=PRIMARY, foreground="#ffffff",
                    font=FONT_TITLE)
    style.configure("Subtitle.TLabel", background=PRIMARY, foreground="#e3e9ff",
                    font=FONT_SMALL)
    style.configure("Accent.TLabel", background=CARD, foreground=ACCENT, font=FONT_BOLD)
    style.configure("Primary.TLabel", background=BG, foreground=PRIMARY, font=FONT_BOLD)

    # 按钮：扁平 + 柔和悬停
    style.configure("TButton", background="#ffffff", foreground=TEXT, borderwidth=1,
                    focusthickness=0, padding=(14, 7), relief="solid",
                    bordercolor=BORDER, cursor="hand2")
    style.map("TButton",
              background=[("pressed", PRIMARY_LIGHT), ("active", "#f2f5ff")],
              bordercolor=[("pressed", PRIMARY), ("active", PRIMARY)],
              foreground=[("disabled", MUTED)])
    # 主色按钮（主行动点）
    style.configure("Accent.TButton", background=PRIMARY, foreground="#ffffff",
                    bordercolor=PRIMARY, padding=(18, 8), cursor="hand2",
                    font=FONT_BOLD)
    style.map("Accent.TButton",
              background=[("pressed", PRIMARY_PRESSED), ("active", PRIMARY_DARK)],
              bordercolor=[("pressed", PRIMARY_PRESSED), ("active", PRIMARY_DARK)],
              foreground=[("disabled", DISABLED_FG)])
    # 危险按钮
    style.configure("Danger.TButton", background="#ffffff", foreground=DANGER,
                    bordercolor="#f6cfD1", cursor="hand2", padding=(12, 7))
    style.map("Danger.TButton",
              background=[("active", "#fef1f1"), ("pressed", "#fbdfe0")],
              bordercolor=[("active", DANGER)])

    # 输入框
    style.configure("TEntry", fieldbackground=INPUT_BG, foreground=TEXT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    padding=5, relief="solid", insertcolor=TEXT)
    style.map("TEntry", bordercolor=[("focus", PRIMARY)],
              lightcolor=[("focus", PRIMARY)], darkcolor=[("focus", PRIMARY)])
    style.configure("TCombobox", fieldbackground=INPUT_BG, foreground=TEXT,
                    background="#ffffff", arrowcolor=MUTED, bordercolor=BORDER,
                    padding=4)
    style.map("TCombobox", bordercolor=[("focus", PRIMARY)],
              fieldbackground=[("readonly", "#ffffff")],
              foreground=[("readonly", TEXT)])

    # 单选/复选
    style.configure("TRadiobutton", background=BG, foreground=TEXT, indicatoron=1)
    style.map("TRadiobutton", background=[("active", BG)])
    style.configure("TCheckbutton", background=BG, foreground=TEXT, indicatoron=1)
    style.map("TCheckbutton", background=[("active", BG)])

    # 隐藏原生页签条：所有页签均由 mcl/ui/navbar.py 的 NavTabs 自绘
    # （带颜色渐变 + 指示条滑动动画）。
    # 关键：ttk.Notebook 的页签行由控件自身用 Notebook.tab 元素绘制，
    # 样式名为 TNotebook.Tab，与 TNotebook 布局无关 ——
    # 必须把 TNotebook.Tab 的布局置空才能隐藏页签行。
    try:
        style.layout("TNotebook.Tab", [])
        style.configure("TNotebook", tabmargins=0)
    except Exception:
        pass

    # Treeview：斑马纹由调用方配 tag，这里统一行高与表头
    style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff",
                    foreground=TEXT, rowheight=28, bordercolor=BORDER,
                    relief="solid", borderwidth=1)
    style.map("Treeview",
              background=[("selected", SELECT)],
              foreground=[("selected", PRIMARY_DARK)])
    style.configure("Treeview.Heading", background="#f4f6fb", foreground=MUTED,
                    font=FONT_BOLD, padding=6, relief="flat")
    style.map("Treeview.Heading", background=[("active", "#e9edf5")])

    # 滚动条
    style.configure("Vertical.TScrollbar", background="#d3d9e6", troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", "#b9c2d8")])
    style.configure("Horizontal.TScrollbar", background="#d3d9e6", troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, relief="flat")
    style.map("Horizontal.TScrollbar", background=[("active", "#b9c2d8")])

    # 进度条：更粗、主色填充
    style.configure("Horizontal.TProgressbar", background=PRIMARY,
                    troughcolor="#e2e7f0", bordercolor="#e2e7f0",
                    lightcolor=PRIMARY, darkcolor=PRIMARY, thickness=12)

    # Spinbox
    style.configure("TSpinbox", fieldbackground=INPUT_BG, foreground=TEXT,
                    bordercolor=BORDER, arrowcolor=MUTED, padding=4)

    # 按下态样式：配合 anim.bind_click 做点击反馈（延迟导入避免循环）
    try:
        from . import anim
        anim.install_pressed_styles(style)
    except Exception:
        pass

    return style


def lerp_color(c1: str, c2: str, t: float) -> str:
    """两个 #rrggbb 颜色线性插值，用于渐变绘制。"""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"
