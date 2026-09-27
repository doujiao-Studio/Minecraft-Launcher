"""通用自绘页签导航条。

接管 ttk.Notebook 的原生页签条，换成自绘按钮，让「未选中 → 选中」
的状态切换带**颜色渐变**动画 + 主色下划线**滑动**动画。

用法（注意：NavTabs 要 pack 在 notebook 之前，否则会被 expand 挤出可视区）：

    nb = ttk.Notebook(parent)
    nb.add(page1, text="页一")
    nav = NavTabs(parent, nb)
    nav.pack(fill="x", padx=14, pady=(8, 4))
    nb.pack(fill="both", expand=True, padx=14)
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from . import anim, theme

# 隐藏原生页签行：页签由控件自身以 Notebook.tab 元素绘制（样式 TNotebook.Tab），
# 与 TNotebook 布局无关，必须把 Tab 样式布局置空。
_TAB_LAYOUT: list = []


def _ensure_style() -> None:
    """兜底：确保原生页签行被隐藏（幂等）。"""
    try:
        style = ttk.Style()
        if style.layout("TNotebook.Tab") != _TAB_LAYOUT:
            style.layout("TNotebook.Tab", _TAB_LAYOUT)
            style.configure("TNotebook", tabmargins=0)
    except Exception:
        pass


class NavTabs(tk.Frame):
    """自绘页签条：文字颜色渐变 + 指示条滑动。"""

    HOVER_BG = "#e3e8f2"         # 悬停底色
    HOVER_MS = anim.HOVER_MS     # 悬停底色渐变时长
    FOCUS_MS = anim.FOCUS_MS     # 选中色渐变时长
    SLIDE_MS = anim.SLIDE_MS     # 指示条滑动时长

    def __init__(self, master, notebook, bg: str | None = None, **kw):
        super().__init__(master, bg=bg or theme.BG, height=42, **kw)
        self.nb = notebook
        self._bg = bg or theme.BG
        _ensure_style()

        # 依据 notebook 现有页签生成按钮
        self._buttons: list[tk.Label] = []
        try:
            count = len(self.nb.tabs())
        except Exception:
            count = 0
        for i in range(count):
            try:
                text = (self.nb.tab(i, "text") or "").strip()
            except Exception:
                text = ""
            b = tk.Label(self, text=text, bg=self._bg, fg=theme.TEXT,
                         font=theme.FONT, padx=14, pady=7, cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda _e, idx=i: self.select(idx))
            b.bind("<Enter>", lambda _e, idx=i: self._hover(idx, True))
            b.bind("<Leave>", lambda _e, idx=i: self._hover(idx, False))
            anim.bind_click(b)
            self._buttons.append(b)

        # 主色下滑动指示条
        self._ind = tk.Frame(self, bg=theme.PRIMARY, height=3)
        self._ind_x = 0
        self._ind_w = 0
        try:
            self._active = self.nb.index("current")
        except Exception:
            self._active = 0
        self._apply_colors(self._active, animate=False)
        self.nb.bind("<<NotebookTabChanged>>", self._on_changed, add="+")
        self.after(60, lambda: self._place_indicator(self._active, animate=False))

    # ---------------- 对外 ----------------
    def select(self, idx: int) -> None:
        """切到指定页签（动画由 NotebookTabChanged 回调播放）。"""
        try:
            if idx != self.nb.index("current"):
                self.nb.select(idx)
        except Exception:
            pass

    def active_index(self) -> int:
        return self._active

    # ---------------- 内部 ----------------
    def _hover(self, idx: int, entering: bool) -> None:
        if idx == self._active or not (0 <= idx < len(self._buttons)):
            return
        btn = self._buttons[idx]
        try:
            anim.tween_color(btn, "bg", self._bg if entering else self.HOVER_BG,
                             self.HOVER_BG if entering else self._bg,
                             ms=self.HOVER_MS)
        except Exception:
            pass

    def _on_changed(self, _e=None) -> None:
        try:
            idx = self.nb.index("current")
        except Exception:
            return
        if idx == self._active:
            return
        prev = self._active
        self._active = idx
        self._apply_colors(idx, animate=True, prev=prev)
        self._place_indicator(idx, animate=True)

    def _apply_colors(self, idx: int, animate: bool, prev: int = -1) -> None:
        btns = self._buttons
        if animate:
            if 0 <= prev < len(btns):
                anim.tween_color(btns[prev], "fg", theme.PRIMARY, theme.TEXT,
                                 ms=self.FOCUS_MS)
                anim.tween_color(btns[prev], "bg", btns[prev].cget("bg"), self._bg,
                                 ms=self.HOVER_MS)
            if 0 <= idx < len(btns):
                anim.tween_color(btns[idx], "fg", theme.TEXT, theme.PRIMARY,
                                 ms=self.FOCUS_MS)
                anim.tween_color(btns[idx], "bg", btns[idx].cget("bg"), self._bg,
                                 ms=self.HOVER_MS)
        else:
            for i, b in enumerate(btns):
                try:
                    b.configure(fg=theme.PRIMARY if i == idx else theme.TEXT,
                                bg=self._bg)
                except Exception:
                    pass

    def _place_indicator(self, idx: int, animate: bool = True) -> None:
        if not self._buttons:
            return
        b = self._buttons[idx]
        bx = b.winfo_x()
        bw = max(b.winfo_width(), 1)
        if bw <= 1:
            # 布局尚未完成，稍后重试拿到真实宽度
            self.after(60, lambda: self._place_indicator(idx, animate=False))
            return
        if animate and self._ind_w > 1:
            x0, w0 = self._ind_x, self._ind_w

            def step(t):
                x = round(x0 + (bx - x0) * t)
                w = round(w0 + (bw - w0) * t)
                self._ind_x, self._ind_w = x, w
                self._ind.place_configure(x=x, width=w)

            anim.tween(self, step, ms=self.SLIDE_MS, steps=12,
                       on_done=lambda: self._ind.place_configure(x=bx, width=bw)
                       if self.winfo_exists() else None)
        else:
            self._ind_x, self._ind_w = bx, bw
            self._ind.place(x=bx, rely=1.0, y=0, anchor="sw", width=bw, height=3)
