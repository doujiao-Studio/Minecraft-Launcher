"""通用 UI 部件：线程安全的控制台、表单行、进度行。"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from . import bus


class CardGrid(tk.Frame):
    """可滚动卡片网格：列数随宽度自适应，卡片铺满每一行。

    用于模组/资源包列表，替代原来的表格，让列表铺满整页。
    """

    def __init__(self, master, card_w: int = 320, card_h: int = 104,
                 pad: int = 10, bg=None):
        super().__init__(master)
        self._bg = bg if bg is not None else "#eef1f7"
        self.card_w, self.card_h, self.pad = card_w, card_h, pad
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self._bg)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=self._bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Enter>", self._grab_wheel)
        self.canvas.bind("<Leave>", self._release_wheel)
        self.inner.bind("<Enter>", self._grab_wheel)
        self._cards: list = []
        self._cols = 1

    def clear(self) -> None:
        for c in self._cards:
            try:
                c.destroy()
            except Exception:
                pass
        self._cards = []
        self.canvas.yview_moveto(0)
        self.canvas.configure(scrollregion=(0, 0, 0, 0))

    def add(self, card) -> None:
        self._cards.append(card)
        self._relayout()

    @property
    def cards(self) -> list:
        return self._cards

    def _on_resize(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        self._relayout()

    def _relayout(self) -> None:
        if not self._cards:
            return
        w = self.canvas.winfo_width() or (self.card_w + self.pad) * 2
        cols = max(1, int((w - self.pad) // (self.card_w + self.pad)))
        for i, c in enumerate(self._cards):
            c.grid(row=i // cols, column=i % cols,
                   padx=self.pad // 2, pady=self.pad // 2, sticky="nsew")
        for col in range(cols):
            self.inner.grid_columnconfigure(col, weight=1, uniform="cardcol")
        self._cols = cols
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _grab_wheel(self, _e):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _release_wheel(self, _e):
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass

    def _on_wheel(self, e):
        self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")


class Console(tk.Frame):
    """日志/控制台：可从任意线程 append。自动裁剪旧行，防止长时间运行卡顿。"""

    MAX_LINES = 4000  # 超出后丢弃最旧的 1/4

    def __init__(self, master, height=12, state="disabled"):
        super().__init__(master)
        self.text = tk.Text(self, height=height, wrap="word", state="normal",
                            bg="#0d1117", fg="#c9d1d9", insertbackground="#c9d1d9",
                            font=("Consolas", 10))
        sb = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self._last = ""
        self._state = state

    def append(self, line: str) -> None:
        if line == self._last:
            line = line + " (重复)"
        self._last = line
        if not line.endswith("\n"):
            line += "\n"
        bus.dispatch(lambda l=line: self._write(l))

    def _write(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line)
        # 裁剪：行数超过上限时删除最旧的 1/4，避免 Text 控件无限膨胀卡顿
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > self.MAX_LINES:
            cut = lines - self.MAX_LINES + self.MAX_LINES // 4
            self.text.delete("1.0", f"{cut}.0")
        self.text.see("end")
        if self._state == "disabled":
            self.text.configure(state="disabled")

    def clear(self) -> None:
        bus.dispatch(self._clear)

    def _clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if self._state == "disabled":
            self.text.configure(state="disabled")

    def on_command(self, callback) -> None:
        self.text.bind("<Return>", lambda e: callback(self._input()) and "break")

    def _input(self) -> str:
        return ""


class Labeled(ttk.Frame):
    """左侧标签 + 右侧控件的表单行。"""

    def __init__(self, master, label, widget=None, label_width=12):
        super().__init__(master)
        self.lbl = ttk.Label(self, text=label, width=label_width, anchor="w")
        self.lbl.pack(side="left", padx=(0, 6))
        self.field = widget if widget is not None else ttk.Frame(self)
        self.field.pack(side="left", fill="x", expand=True)


def make_progress(master) -> ttk.Progressbar:
    bar = ttk.Progressbar(master, mode="determinate", maximum=1000, value=0)
    return bar


def set_progress(bar: ttk.Progressbar, done: float, total: float) -> None:
    if total <= 0:
        return
    bus.dispatch(lambda d=done, t=total: bar.configure(value=int(d / t * 1000)))


class ToolTip:
    """悬停提示气泡：给按钮/控件加说明，提升交互手感。"""

    def __init__(self, widget, text: str, delay: int = 600):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip = None
        self._after = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e):
        self._after = self.widget.after(self.delay, self._show)

    def _leave(self, _e):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None
        self._hide()

    def _show(self):
        self._hide()
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        frame = tk.Frame(self.tip, bg="#22262b")
        frame.pack()
        tk.Label(frame, text=self.text, bg="#22262b", fg="#ffffff",
                 font=("Microsoft YaHei UI", 9), padx=8, pady=4,
                 justify="left").pack()

    def _hide(self):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


class ScrollableFrame(ttk.Frame):
    """垂直滚动容器：内容超出可视区时出现滚动条，用于内容较多的页面。

    滚轮事件只在鼠标进入容器时接管（离开时解除全局绑定），
    避免多个实例共存时 bind_all 互相干扰与泄漏。"""

    def __init__(self, master, bg=None, **kw):
        super().__init__(master, **kw)
        self._bg = bg if bg is not None else "#eef1f7"
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self._bg)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, padding=(2, 2))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", self._grab_wheel)
        self.canvas.bind("<Leave>", self._release_wheel)
        # 子控件也需要触发接管：递归绑定
        self.inner.bind("<Enter>", self._grab_wheel)
        self.bind("<Destroy>", lambda e: self._release_wheel(None))

    def _on_inner(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _grab_wheel(self, _e):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _release_wheel(self, _e):
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass

    def _on_wheel(self, e):
        self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
