"""通用工具：日志、线程、哈希、原子写。"""
from __future__ import annotations
import hashlib
import logging
import logging.handlers
import os
import sys
import threading
import time
from typing import Callable

from . import paths

_LOG_INITED = False
_LOG_LOCK = threading.Lock()


def _init_log() -> None:
    global _LOG_INITED
    with _LOG_LOCK:
        if _LOG_INITED:
            return
        os.makedirs(paths.log_dir(), exist_ok=True)
        # 轮转日志：单文件最大 1MB、保留 3 个备份，避免 mcl.log 无限膨胀
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(paths.log_dir(), "mcl.log"), maxBytes=1024 * 1024,
            backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        root.addHandler(logging.StreamHandler(sys.stdout))
        _LOG_INITED = True


def get_logger(name: str = "mcl") -> logging.Logger:
    _init_log()
    return logging.getLogger(name)


def sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha1_file(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: str, data: bytes) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def run_thread(fn: Callable[..., None], name: str = "worker", daemon: bool = True,
               args: tuple = ()) -> threading.Thread:
    t = threading.Thread(target=fn, name=name, daemon=daemon, args=args)
    t.start()
    return t


def now() -> float:
    return time.time()


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def seconds_hms(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}时{m}分{s}秒"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"
