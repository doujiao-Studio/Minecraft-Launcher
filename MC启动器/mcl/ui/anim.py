"""UI 动效：按钮点击反馈、状态切换颜色渐变、位置补间、卡片悬停与按下。

设计原则：只用 Tk 原生能力（状态位 / 样式切换 / 定时帧），
不引入额外依赖，不阻塞主线程，动画时长控制在 90~200ms，保证手感干脆。
"""
from __future__ import annotations
import time
import tkinter as tk
from tkinter import ttk

from . import theme

PRESS_MS = 110          # 按钮按下态停留时间
HOVER_MS = 90           # 悬停底色渐变时长
FOCUS_MS = 180          # 选中态颜色渐变时长
SLIDE_MS = 200          # 指示条滑动时长

# 基础样式 -> 按下态样式（更深的底色 + 更小的内边距，形成“按下去”的观感）
_PRESSED_STYLE = {
    "TButton": "Pressed.TButton",
    "Accent.TButton": "AccentPressed.TButton",
    "Danger.TButton": "DangerPressed.TButton",
}

_ANIM_FLAG = "_mcl_click_bound"


# ------------------------------------------------------------------
#  通用补间动画（颜色渐变、位置滑动等）
# ------------------------------------------------------------------
def tween(after_source, fn, ms: int = 160, steps: int = 10, on_done=None) -> None:
    """通用补间：每帧调用 fn(t)，t 为 ease-out 后的进度 0~1。

    after_source：借用其 after() 调度帧的控件；fn 里操作控件抛出
    TclError（控件已销毁）时自动停止。
    """
    dur = max(ms, 1) / 1000
    interval = max(int(ms / steps), 10)
    start = time.perf_counter()

    def frame():
        t = min(1.0, (time.perf_counter() - start) / dur)
        te = 1 - (1 - t) ** 3      # ease-out cubic
        try:
            fn(te)
        except tk.TclError:
            return
        if t < 1.0:
            after_source.after(interval, frame)
        elif on_done:
            try:
                on_done()
            except tk.TclError:
                pass

    frame()


def tween_color(widget, prop: str, from_c: str, to_c: str,
                ms: int = 160, steps: int = 10, on_done=None) -> None:
    """把 widget 的 fg/bg/highlightbackground 等颜色属性从 from_c 渐变到 to_c。"""
    tween(widget, lambda t: widget.configure(**{prop: _mix(from_c, to_c, t)}),
          ms=ms, steps=steps, on_done=on_done)


# ------------------------------------------------------------------
#  按钮点击动画
# ------------------------------------------------------------------
def bind_click(widget) -> None:
    """给 ttk/tk 控件挂上点击动画（重复调用安全）。

    - ttk 控件：按下时切到 xxxPressed 样式（底色加深 + 内边距收 1px），
      110ms 后回弹，配合已有的 pressed 样式映射形成明显反馈。
    - tk 控件（Label/Frame/Canvas）：瞬间提亮底色后恢复。
    """
    if widget is None or getattr(widget, _ANIM_FLAG, False):
        return
    try:
        setattr(widget, _ANIM_FLAG, True)
    except Exception:
        return

    base_style = _base_style(widget)
    pressed_style = _PRESSED_STYLE.get(base_style)

    if pressed_style:
        def _press(_e=None):
            try:
                widget.configure(style=pressed_style)
                widget.after(PRESS_MS, _release)
            except Exception:
                pass

        def _release():
            try:
                if widget.winfo_exists():
                    widget.configure(style=base_style)
            except Exception:
                pass
    else:
        # tk 原生控件：底色闪一下
        try:
            base_bg = widget.cget("bg")
        except Exception:
            base_bg = None

        def _press(_e=None):
            if not base_bg:
                return
            try:
                widget.configure(bg=_mix(base_bg, "#000000", 0.18))
                widget.after(PRESS_MS, _release)
            except Exception:
                pass

        def _release():
            try:
                if widget.winfo_exists():
                    widget.configure(bg=base_bg)
            except Exception:
                pass

    widget.bind("<ButtonPress-1>", _press, add="+")


def _base_style(widget) -> str:
    try:
        s = widget.cget("style")
        if s:
            return s
    except Exception:
        pass
    try:
        return widget.winfo_class()
    except Exception:
        return "TButton"


def bind_click_all(root) -> int:
    """递归给窗口内所有按钮类控件挂点击动画，返回绑定数量。"""
    count = 0
    try:
        children = list(root.winfo_children())
    except Exception:
        return 0
    for w in children:
        cls = w.winfo_class() if hasattr(w, "winfo_class") else ""
        if cls in ("TButton", "TCheckbutton", "TRadiobutton"):
            bind_click(w)
            count += 1
        count += bind_click_all(w)
    return count


def press_now(widget) -> None:
    """立刻播放一次点击动画（用于键盘触发等场景）。"""
    try:
        base = _base_style(widget)
        pressed = _PRESSED_STYLE.get(base)
        if not pressed:
            return
        widget.configure(style=pressed)
        widget.after(PRESS_MS, lambda: widget.configure(style=base))
    except Exception:
        pass


#  悬停反馈（卡片等自定义控件）
# ------------------------------------------------------------------
def bind_hover(widget, normal_bg: str, hover_bg: str, normal_bd: str, hover_bd: str):
    """悬停：换底色 + 换描边颜色。"""
    try:
        widget.configure(bg=normal_bg, highlightbackground=normal_bd)
    except Exception:
        return

    def enter(_e=None):
        widget.configure(bg=hover_bg, highlightbackground=hover_bd)

    def leave(_e=None):
        widget.configure(bg=normal_bg, highlightbackground=normal_bd)

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", leave, add="+")
    return enter, leave


def _mix(c1: str, c2: str, t: float) -> str:
    """把 c1 向 c2 混合 t（0~1），用于按下瞬间的底色加深。"""
    try:
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return c1


def install_pressed_styles(style: ttk.Style) -> None:
    """注册按下态样式（在 theme.apply 之后调用）。"""
    style.configure("Pressed.TButton", background=theme.PRIMARY_LIGHT,
                    bordercolor=theme.PRIMARY, padding=(14, 6), relief="solid",
                    foreground=theme.PRIMARY_DARK)
    style.configure("AccentPressed.TButton", background=theme.PRIMARY_PRESSED,
                    bordercolor=theme.PRIMARY_PRESSED, foreground="#ffffff",
                    padding=(18, 7), font=theme.FONT_BOLD)
    style.configure("DangerPressed.TButton", background="#fbdfe0",
                    bordercolor=theme.DANGER, foreground=theme.DANGER,
                    padding=(12, 6))
