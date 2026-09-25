"""通用 UI 部件：线程安全的控制台、表单行、进度行。"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from . import bus


class Console(tk.Frame):
    """日志/控制台：可从任意线程 append。"""

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
    """垂直滚动容器：内容超出可视区时出现滚动条，用于内容较多的页面。"""

    def __init__(self, master, bg=None, **kw):
        super().__init__(master, **kw)
        self._bg = bg if bg is not None else "#f5f6fa"
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self._bg)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, padding=(2, 2))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _on_inner(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _on_wheel(self, e):
        # 仅当鼠标位于本容器内时滚动
        x = self.winfo_pointerx()
        y = self.winfo_pointery()
        try:
            rx = self.winfo_rootx(); ry = self.winfo_rooty()
            if rx <= x <= rx + self.winfo_width() and ry <= y <= ry + self.winfo_height():
                self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        except Exception:
            pass
