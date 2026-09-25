"""线程安全的 UI 调度：工作线程不能直接改 Tk 控件，经队列投递到主线程。"""
from __future__ import annotations
import queue
import threading
from typing import Callable

_q: queue.Queue = queue.Queue()
_polling = False
_root = None


def init(root) -> None:
    global _root, _polling
    _root = root
    if not _polling:
        _polling = True
        _pump()


def dispatch(fn: Callable[[], None]) -> None:
    """从任意线程调用，安全地把函数安排到主线程执行。"""
    _q.put(fn)


def _pump() -> None:
    if _root is None:
        return
    try:
        while True:
            fn = _q.get_nowait()
            try:
                fn()
            except Exception:
                pass
    except queue.Empty:
        pass
    _root.after(50, _pump)


def run_async(fn: Callable[[], None], name: str = "task") -> threading.Thread:
    """在后台线程执行 fn（fn 内部如需改 UI 请用 dispatch）。"""
    t = threading.Thread(target=fn, name=name, daemon=True)
    t.start()
    return t
