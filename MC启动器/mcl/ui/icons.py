"""模组图标：异步下载 + 磁盘缓存 + 主线程安全构造 PhotoImage。

Modrinth 返回的 icon_url 直接可用；下载失败/格式不支持（如 webp）时
回落到占位图，保证列表始终有图可看。
"""
from __future__ import annotations
import hashlib
import os
import threading
import tkinter as tk

from .. import network, paths
from . import bus


class IconLoader:
    """按 URL 取图，缩放到统一尺寸并缓存（内存 + 磁盘）。"""

    def __init__(self, size: int = 64):
        self.size = size
        self.dir = os.path.join(paths.base_dir(), "cache", "icons")
        try:
            os.makedirs(self.dir, exist_ok=True)
        except OSError:
            pass
        self._mem: dict[str, tk.PhotoImage] = {}
        self._bad: set[str] = set()
        self._pending: set[str] = set()
        self._placeholder: tk.PhotoImage | None = None

    # ---- 占位图 ----
    def placeholder(self) -> tk.PhotoImage:
        if self._placeholder is None:
            s = self.size
            img = tk.PhotoImage(width=s, height=s)
            img.put("#eef1f7", to=(0, 0, s, s))
            img.put("#dbe0ee", to=(0, 0, s, 2))
            img.put("#dbe0ee", to=(0, s - 3, s, s))
            img.put("#dbe0ee", to=(0, 0, 2, s))
            img.put("#dbe0ee", to=(s - 3, 0, s, s))
            img.put("#c3cadd", to=(s // 2 - 10, s // 2 - 2, s // 2 + 10, s // 2 + 2))
            self._placeholder = img
        return self._placeholder

    # ---- 同步取缓存 ----
    def cached(self, url: str) -> tk.PhotoImage | None:
        return self._mem.get(url)

    def _local(self, url: str) -> str:
        ext = os.path.splitext(url.split("?")[0])[1].lower()
        if ext not in (".png", ".gif", ".ppm", ".pgm", ".jpg", ".jpeg"):
            ext = ".png"
        name = hashlib.sha1(url.encode("utf-8")).hexdigest() + ext
        return os.path.join(self.dir, name)

    # ---- 异步请求 ----
    def request(self, url: str, on_ready) -> None:
        """on_ready(img) 一定在主线程被调用（无网络时给占位图）。"""
        if not url:
            self._safe(on_ready, self.placeholder())
            return
        img = self._mem.get(url)
        if img is not None:
            self._safe(on_ready, img)
            return
        if url in self._bad or url in self._pending:
            if url in self._bad:
                self._safe(on_ready, self.placeholder())
            return
        self._pending.add(url)
        threading.Thread(target=self._fetch, args=(url, on_ready),
                         daemon=True).start()

    def _fetch(self, url: str, on_ready) -> None:
        dest = self._local(url)
        if not os.path.isfile(dest):
            try:
                network.download(url, dest, timeout=20, retries=2)
            except Exception:
                self._pending.discard(url)
                self._bad.add(url)
                bus.dispatch(lambda: self._safe(on_ready, self.placeholder()))
                return
        bus.dispatch(lambda: self._make(url, dest, on_ready))

    def _make(self, url: str, path: str, on_ready) -> None:
        self._pending.discard(url)
        try:
            img = None
            try:
                img = tk.PhotoImage(file=path)
                img = _fit(img, self.size)
            except Exception:
                # Tk 原生只认 png/gif/ppm；webp/jpg 借助 Pillow 转成 64px PNG
                png = _convert_via_pillow(path, self.size)
                if png:
                    img = tk.PhotoImage(file=png)
            if img is None:
                raise ValueError("unsupported image")
            self._mem[url] = img
            self._safe(on_ready, img)
        except Exception:
            self._bad.add(url)
            self._safe(on_ready, self.placeholder())

    @staticmethod
    def _safe(on_ready, img) -> None:
        try:
            on_ready(img)
        except Exception:
            pass  # 目标控件可能已被销毁


def _convert_via_pillow(path: str, size: int) -> str | None:
    """用 Pillow 把 webp/jpg 等格式转成 size 大小的 PNG；失败返回 None。"""
    try:
        from PIL import Image
    except Exception:
        return None
    out = path + ".png"
    try:
        if not os.path.isfile(out):
            from PIL import Image, ImageOps
            with Image.open(path) as im:
                im = im.convert("RGBA")
                im = ImageOps.fit(im, (size, size))  # 居中裁成统一方块
                im.save(out, "PNG")
        return out
    except Exception:
        try:
            if os.path.isfile(out):
                os.remove(out)
        except OSError:
            pass
        return None


def _fit(img: tk.PhotoImage, size: int) -> tk.PhotoImage:
    """整数倍缩放（subsample/zoom），保证 Tk 支持且不糊得太厉害。"""
    try:
        w = img.width()
    except Exception:
        return img
    if w <= 0:
        return img
    if w > size:
        k = w // size
        if k >= 2:
            img = img.subsample(k, k)
    elif w < size:
        k = min(size // max(w, 1), 8)
        if k >= 2:
            img = img.zoom(k, k)
    return img
