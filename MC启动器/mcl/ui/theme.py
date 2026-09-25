"""全局主题：现代化、干净的配色与控件样式（基于 clam 主题深度定制）。

只定制默认样式类，现有所有控件自动获得新外观，无需逐处修改。
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

# ---- 配色板（现代、干净）----
BG = "#f3f5f9"          # 页面背景
CARD = "#ffffff"        # 卡片/面板背景
PRIMARY = "#3b5bdb"     # 主蓝
PRIMARY_DARK = "#2f49b8"
ACCENT = "#0ca678"      # 成功绿
WARN = "#f59f00"
TEXT = "#22262b"
MUTED = "#868e96"
BORDER = "#e6e9f0"
SELECT = "#dbe4ff"      # 列表选中（浅蓝）
ROW_ALT = "#f8f9fd"

FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 15, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)


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
                    relief="solid", borderwidth=1, padding=8)
    style.configure("TLabelframe.Label", background=CARD, foreground=PRIMARY,
                    font=FONT_BOLD)

    # 标签
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
    style.configure("Title.TLabel", background=PRIMARY, foreground="#ffffff",
                    font=FONT_TITLE)
    style.configure("Subtitle.TLabel", background=PRIMARY, foreground="#dfe3ff",
                    font=FONT_SMALL)
    style.configure("Accent.TLabel", background=CARD, foreground=ACCENT, font=FONT_BOLD)
    style.configure("Primary.TLabel", background=BG, foreground=PRIMARY, font=FONT_BOLD)

    # 按钮
    style.configure("TButton", background="#ffffff", foreground=TEXT, borderwidth=1,
                    focusthickness=0, padding=(12, 6), relief="solid", bordercolor=BORDER,
                    cursor="hand2")
    style.map("TButton",
              background=[("active", "#eef1fb"), ("pressed", "#dbe4ff")],
              bordercolor=[("active", PRIMARY), ("pressed", PRIMARY)])
    # 主色按钮
    style.configure("Accent.TButton", background=PRIMARY, foreground="#ffffff",
                    bordercolor=PRIMARY, padding=(14, 6), cursor="hand2")
    style.map("Accent.TButton",
              background=[("active", PRIMARY_DARK), ("pressed", "#22367f")],
              foreground=[("disabled", "#c0c8e8")])
    # 危险按钮
    style.configure("Danger.TButton", background="#ffffff", foreground="#e03131",
                    bordercolor="#f1c4c4", cursor="hand2")
    style.map("Danger.TButton", background=[("active", "#fff0f0")])

    # 输入框
    style.configure("TEntry", fieldbackground="#ffffff", foreground=TEXT,
                    bordercolor=BORDER, padding=4, relief="solid", insertcolor=TEXT)
    style.map("TEntry", bordercolor=[("focus", PRIMARY)])
    style.configure("TCombobox", fieldbackground="#ffffff", foreground=TEXT,
                    background="#ffffff", arrowcolor=MUTED, bordercolor=BORDER,
                    padding=3)
    style.map("TCombobox", bordercolor=[("focus", PRIMARY)],
              fieldbackground=[("readonly", "#ffffff")])

    # 单选/复选
    style.configure("TRadiobutton", background=BG, foreground=TEXT, indicatoron=1)
    style.map("TRadiobutton", background=[("active", BG)])
    style.configure("TCheckbutton", background=BG, foreground=TEXT, indicatoron=1)
    style.map("TCheckbutton", background=[("active", BG)])

    # Notebook
    style.configure("TNotebook", background=BG, bordercolor=BORDER, borderwidth=1)
    style.configure("TNotebook.Tab", background="#eceef5", foreground=MUTED,
                    padding=(16, 7), font=FONT)
    style.map("TNotebook.Tab",
              background=[("selected", "#ffffff")],
              foreground=[("selected", PRIMARY)],
              bordercolor=[("selected", BORDER)])

    # Treeview
    style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff",
                    foreground=TEXT, rowheight=26, bordercolor=BORDER, relief="solid")
    style.map("Treeview",
              background=[("selected", SELECT)],
              foreground=[("selected", PRIMARY)])
    style.configure("Treeview.Heading", background="#f3f5f9", foreground=MUTED,
                    font=FONT_BOLD, padding=5, relief="flat")
    style.map("Treeview.Heading", background=[("active", "#e9edf5")])

    # 滚动条
    style.configure("Vertical.TScrollbar", background="#d5dae6", troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, relief="flat")
    style.configure("Horizontal.TScrollbar", background="#d5dae6", troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, relief="flat")

    # 进度条
    style.configure("Horizontal.TProgressbar", background=PRIMARY,
                    troughcolor="#e6e9f0", bordercolor="#e6e9f0", thickness=10)

    return style
