"""版本详情窗口：点进某个已安装版本，查看 模组 / 资源包 / 存档 / 数据包。

入口：版本管理页双击某一行，或选中后点「查看详情」。
所有目录扫描都在后台线程做，主线程只负责填表，避免大存档目录卡顿。
"""
from __future__ import annotations
import gzip
import os
import shutil
import struct
import tkinter as tk
from tkinter import ttk, messagebox

from .. import paths
from . import bus, navbar, theme

GAMEMODE = {0: "生存", 1: "创造", 2: "冒险", 3: "旁观"}
DIFFICULTY = {0: "和平", 1: "简单", 2: "普通", 3: "困难"}


# ==================================================================
#  扫描（纯函数，便于测试）
# ==================================================================
def human_size(n: float) -> str:
    from ..utils import human_size as _h
    return _h(n)


def dir_size(path: str, cap: int = 30000) -> int:
    """递归统计目录大小；文件数超过 cap 就停止（防止超大存档卡死）。"""
    total = 0
    count = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    count += 1
                    if count > cap:
                        return total
                    try:
                        if e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                        elif e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def _mtime_str(ts: float) -> str:
    import time as _t
    try:
        return _t.strftime("%Y-%m-%d %H:%M", _t.localtime(float(ts or 0)))
    except Exception:
        return ""


def _entry(name: str, path: str, kind: str, size: int, mtime: float,
           **extra) -> dict:
    d = {"name": name, "path": path, "kind": kind, "size": size,
         "mtime": mtime, "detail": ""}
    d.update(extra)
    return d


def scan_mods(game_dir: str) -> list[dict]:
    """mods 目录：.jar 即启用，.jar.disabled 为已禁用。"""
    out = []
    d = os.path.join(game_dir, "mods")
    if not os.path.isdir(d):
        return out
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        p = os.path.join(d, n)
        if not os.path.isfile(p):
            continue
        low = n.lower()
        if low.endswith(".jar") or low.endswith(".jar.disabled") or low.endswith(".zip"):
            disabled = low.endswith(".disabled")
            show = n
            for suf in (".disabled",):
                if show.lower().endswith(suf):
                    show = show[: -len(suf)]
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append(_entry(show, p, "mod", st.st_size, st.st_mtime,
                              enabled=not disabled,
                              detail="已禁用" if disabled else "已启用"))
    return out


def scan_resourcepacks(game_dir: str) -> list[dict]:
    """resourcepacks 目录：.zip 或含 pack.mcmeta 的文件夹。"""
    out = []
    d = os.path.join(game_dir, "resourcepacks")
    if not os.path.isdir(d):
        return out
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        p = os.path.join(d, n)
        is_pack = False
        if os.path.isfile(p) and n.lower().endswith(".zip"):
            is_pack = True
        elif os.path.isdir(p) and os.path.isfile(os.path.join(p, "pack.mcmeta")):
            is_pack = True
        if not is_pack:
            continue
        size = os.path.getsize(p) if os.path.isfile(p) else dir_size(p)
        try:
            st = os.stat(p)
        except OSError:
            continue
        out.append(_entry(n, p, "resourcepack", size, st.st_mtime,
                          detail="文件夹" if os.path.isdir(p) else "ZIP 包"))
    return out


def scan_saves(game_dir: str) -> list[dict]:
    """saves 目录：每个子目录一个存档，读 level.dat 拿世界名/模式/最后游玩。"""
    out = []
    d = os.path.join(game_dir, "saves")
    if not os.path.isdir(d):
        return out
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        p = os.path.join(d, n)
        if not os.path.isdir(p) or n.startswith("."):
            continue
        meta = read_level_dat(os.path.join(p, "level.dat"))
        size = dir_size(p)
        try:
            mtime = os.stat(p).st_mtime
        except OSError:
            mtime = 0
        last = float(meta.get("LastPlayed", 0) or 0) / 1000.0 or mtime
        gm = meta.get("GameType")
        ver = (meta.get("Version") or {}).get("Name") if isinstance(
            meta.get("Version"), dict) else None
        bits = []
        if gm is not None:
            try:
                bits.append(GAMEMODE.get(int(gm), f"模式{gm}"))
            except Exception:
                pass
        if ver:
            bits.append(str(ver))
        out.append(_entry(meta.get("LevelName") or n, p, "save", size, last,
                          detail=" · ".join(bits),
                          icon=os.path.join(p, "icon.png"),
                          dir_name=n))
    out.sort(key=lambda x: x.get("mtime") or 0, reverse=True)
    return out


def scan_datapacks(game_dir: str) -> list[dict]:
    """数据包：全局 datapacks 目录 + 各存档内的 datapacks。"""
    out = []
    roots = [(os.path.join(game_dir, "datapacks"), "全局")]
    saves = os.path.join(game_dir, "saves")
    if os.path.isdir(saves):
        try:
            for n in sorted(os.listdir(saves)):
                sp = os.path.join(saves, n, "datapacks")
                if os.path.isdir(sp):
                    roots.append((sp, f"存档 {n}"))
        except OSError:
            pass
    for root, scope in roots:
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for n in names:
            p = os.path.join(root, n)
            is_pack = (os.path.isfile(p) and n.lower().endswith(".zip")) or \
                      (os.path.isdir(p) and os.path.isfile(
                          os.path.join(p, "pack.mcmeta")))
            if not is_pack:
                continue
            size = os.path.getsize(p) if os.path.isfile(p) else dir_size(p)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append(_entry(n, p, "datapack", size, st.st_mtime, detail=scope))
    return out


# ==================================================================
#  极简 NBT 读取（只读 level.dat 需要的几个字段）
# ==================================================================
def read_level_dat(path: str) -> dict:
    """解析 level.dat（gzip NBT）里的常用字段；失败返回空 dict。"""
    try:
        with gzip.open(path, "rb") as f:
            raw = f.read(1 << 20)  # 前面几 KB 就够
    except Exception:
        return {}
    try:
        _name, top, _end = _nbt_read(raw, 0)
    except Exception:
        return {}
    if isinstance(top, dict):
        data = top.get("Data") if isinstance(top.get("Data"), dict) else top
        return data if isinstance(data, dict) else {}
    return {}


def _nbt_read(raw: bytes, pos: int):
    """读一个完整 tag：返回 (name, value, new_pos)。"""
    tag = raw[pos]
    pos += 1
    if tag == 0:  # End
        return "", None, pos
    ln = struct.unpack(">H", raw[pos:pos + 2])[0]
    pos += 2
    name = raw[pos:pos + ln].decode("utf-8", "replace")
    pos += ln
    val, pos = _nbt_payload(raw, pos, tag)
    return name, val, pos


def _nbt_payload(raw: bytes, pos: int, tag: int):
    if tag == 1:
        return struct.unpack(">b", raw[pos:pos + 1])[0], pos + 1
    if tag == 2:
        return struct.unpack(">h", raw[pos:pos + 2])[0], pos + 2
    if tag == 3:
        return struct.unpack(">i", raw[pos:pos + 4])[0], pos + 4
    if tag == 4:
        return struct.unpack(">q", raw[pos:pos + 8])[0], pos + 8
    if tag == 5:
        return struct.unpack(">f", raw[pos:pos + 4])[0], pos + 4
    if tag == 6:
        return struct.unpack(">d", raw[pos:pos + 8])[0], pos + 8
    if tag == 7:
        n = struct.unpack(">i", raw[pos:pos + 4])[0]
        return raw[pos + 4:pos + 4 + n], pos + 4 + n
    if tag == 8:
        n = struct.unpack(">H", raw[pos:pos + 2])[0]
        return raw[pos + 2:pos + 2 + n].decode("utf-8", "replace"), pos + 2 + n
    if tag == 9:
        itype = raw[pos]
        pos += 1
        n = struct.unpack(">i", raw[pos:pos + 4])[0]
        pos += 4
        items = []
        for _ in range(n):
            v, pos = _nbt_payload(raw, pos, itype)
            items.append(v)
        return items, pos
    if tag == 10:
        out: dict = {}
        while pos < len(raw) and raw[pos] != 0:
            k, v, pos = _nbt_read(raw, pos)
            out[k] = v
        return out, pos + 1  # 吃掉 End
    if tag in (11, 12):
        n = struct.unpack(">i", raw[pos:pos + 4])[0]
        width = 4 if tag == 11 else 8
        return raw[pos + 4:pos + 4 + n * width], pos + 4 + n * width
    raise ValueError(f"unknown nbt tag {tag}")


# ==================================================================
#  详情窗口
# ==================================================================
class VersionDetailWindow(tk.Toplevel):
    """某个版本的详情：模组 / 资源包 / 存档 / 数据包 四个子页。"""

    def __init__(self, master, version_id: str):
        super().__init__(master)
        self.vid = version_id
        self.game_dir = paths.game_dir(version_id)
        self.title(f"版本详情 · {version_id}")
        self.geometry("920x640")
        self.minsize(760, 520)
        self.configure(bg=theme.BG)
        try:
            self.transient(master)
        except Exception:
            pass
        self._icons: list = []          # 防止 PhotoImage 被 GC
        self._panes: list[DetailPane] = []

        self._build_header()
        nb = ttk.Notebook(self)
        for title, kind in (("模组", "mod"), ("资源包", "resourcepack"),
                            ("存档", "save"), ("数据包", "datapack")):
            pane = DetailPane(nb, self, kind)
            nb.add(pane, text=f"  {title}  ")
            self._panes.append(pane)
        self.nav = navbar.NavTabs(self, nb)
        self.nav.pack(fill="x", padx=12, pady=(6, 2))
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        try:
            from . import anim
            anim.bind_click_all(self)
        except Exception:
            pass
        self.after(150, self.refresh_all)

    # ---- 顶部信息条 ----
    def _build_header(self):
        head = tk.Frame(self, bg=theme.CARD, highlightbackground=theme.BORDER,
                        highlightthickness=1)
        head.pack(fill="x", padx=12, pady=(10, 6))
        # 先占右侧按钮，避免长路径把它挤出可视区
        ttk.Button(head, text="打开游戏目录",
                   command=self._open_game_dir).pack(side="right", padx=12, pady=10)
        tk.Label(head, text=self.vid, bg=theme.CARD, fg=theme.PRIMARY,
                 font=theme.FONT_TITLE).pack(side="left", padx=(12, 10), pady=10)
        info = self._summary()
        tk.Label(head, text=info, bg=theme.CARD, fg=theme.MUTED,
                 font=theme.FONT_SMALL, justify="left").pack(side="left", pady=10)

    def _summary(self) -> str:
        vdir = paths.version_dir(self.vid)
        vtype, jver = "未知", ""
        try:
            import json
            with open(os.path.join(vdir, "version.json"), "r", encoding="utf-8") as f:
                vj = json.load(f)
            vtype = {"release": "正式版", "snapshot": "快照",
                     "old_beta": "旧测试版", "old_alpha": "旧Alpha"}.get(
                         vj.get("type"), vj.get("type", "未知"))
            mv = (vj.get("javaVersion") or {}).get("majorVersion")
            jver = f" · Java {mv}" if mv else ""
        except Exception:
            pass
        client = os.path.join(vdir, "client.jar")
        size = human_size(os.path.getsize(client)) if os.path.exists(client) else "-"
        return f"{vtype}{jver} · 客户端 {size}\n{self.game_dir}"

    def _open_game_dir(self):
        try:
            os.makedirs(self.game_dir, exist_ok=True)
            os.startfile(self.game_dir)
        except Exception as e:
            messagebox.showerror("打开失败", str(e), parent=self)

    # ---- 扫描 ----
    def refresh_all(self):
        for p in self._panes:
            p.set_busy(True)
        bus.run_async(self._scan_all, "version-detail")

    def _scan_all(self):
        try:
            mods = scan_mods(self.game_dir)
            rps = scan_resourcepacks(self.game_dir)
            saves = scan_saves(self.game_dir)
            dps = scan_datapacks(self.game_dir)
        except Exception as e:
            bus.dispatch(lambda e=e: messagebox.showerror(
                "扫描失败", str(e), parent=self))
            return
        bus.dispatch(lambda m=mods, r=rps, s=saves, d=dps: self._fill(m, r, s, d))

    def _fill(self, mods, rps, saves, dps):
        try:
            for pane, items in zip(self._panes, (mods, rps, saves, dps)):
                pane.fill(items)
                pane.set_busy(False)
        except Exception:
            pass


# ==================================================================
#  单个子页
# ==================================================================
class DetailPane(ttk.Frame):
    KIND_LABEL = {"mod": "模组", "resourcepack": "资源包",
                  "save": "存档", "datapack": "数据包"}

    def __init__(self, master, win: VersionDetailWindow, kind: str):
        super().__init__(master, padding=8)
        self.win = win
        self.kind = kind
        self.items: list[dict] = []
        self._build_toolbar()
        self._build_list()

    # ---- 界面 ----
    def _build_toolbar(self):
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="刷新", command=self.win.refresh_all).pack(side="left")
        ttk.Button(row, text="打开所在文件夹",
                   command=self.open_folder).pack(side="left", padx=6)
        if self.kind == "mod":
            self.toggle_btn = ttk.Button(row, text="禁用 / 启用",
                                         command=self.toggle_mod)
            self.toggle_btn.pack(side="left")
        if self.kind != "save":
            ttk.Button(row, text="删除", style="Danger.TButton",
                       command=self.delete_item).pack(side="right")
        self.count_var = tk.StringVar(value="")
        ttk.Label(row, textvariable=self.count_var, style="Muted.TLabel").pack(
            side="right", padx=10)

    def _build_list(self):
        f = ttk.Frame(self, style="Card.TFrame")
        f.pack(fill="both", expand=True)
        cols = ("detail", "size", "time")
        self.tree = ttk.Treeview(f, columns=cols, show="tree headings")
        self.tree.heading("#0", text=self.KIND_LABEL.get(self.kind, "名称"))
        self.tree.heading("detail", text="说明")
        self.tree.heading("size", text="大小")
        self.tree.heading("time", text="时间")
        self.tree.column("#0", width=300, anchor="w")
        self.tree.column("detail", width=180, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("time", width=130, anchor="e")
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        vsb.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.tree.tag_configure("off", foreground=theme.MUTED)
        self.empty_var = tk.StringVar(value="")
        self.empty_lbl = ttk.Label(self, textvariable=self.empty_var,
                                   style="Muted.TLabel")

    # ---- 填充 ----
    def set_busy(self, busy: bool):
        try:
            self.count_var.set("扫描中…" if busy else self.count_var.get())
        except Exception:
            pass

    def fill(self, items: list[dict]):
        self.items = items or []
        self.tree.delete(*self.tree.get_children())
        self.win._icons.clear()
        for i, it in enumerate(self.items):
            iid = f"i{i}"
            tags = ()
            if self.kind == "mod" and not it.get("enabled", True):
                tags = ("off",)
            img = ""
            if self.kind == "save":
                img = self._save_icon(it.get("icon", ""))
            self.tree.insert("", "end", iid=iid, text=it.get("name", ""),
                             image=img, tags=tags,
                             values=(it.get("detail", ""),
                                     human_size(it.get("size", 0)),
                                     _mtime_str(it.get("mtime", 0))))
        total = sum(i.get("size", 0) for i in self.items)
        self.count_var.set(f"共 {len(self.items)} 项 · {human_size(total)}")
        if not self.items:
            tip = {"mod": "还没有装模组 —— 可到「下载中心」搜索安装，或用版本管理页的「添加模组」",
                   "resourcepack": "还没有资源包 —— 可到「下载中心 → 资源包」安装",
                   "save": "还没有存档 —— 进游戏创建世界后回来就能看到",
                   "datapack": "还没有数据包（数据包位于各存档的 datapacks 目录）"}
            self.empty_var.set(tip.get(self.kind, "暂无内容"))
            self.empty_lbl.pack(pady=16)
        else:
            self.empty_var.set("")
            try:
                self.empty_lbl.pack_forget()
            except Exception:
                pass

    def _save_icon(self, path: str):
        if not path or not os.path.isfile(path):
            return ""
        try:
            img = tk.PhotoImage(file=path)
            w = img.width()
            if w > 40:
                k = max(1, w // 40)
                img = img.subsample(k, k)
            self.win._icons.append(img)
            return img
        except Exception:
            return ""

    # ---- 行为 ----
    def _selected(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            idx = int(sel[0][1:])
        except Exception:
            return None
        return self.items[idx] if 0 <= idx < len(self.items) else None

    def _need(self) -> dict | None:
        it = self._selected()
        if not it:
            messagebox.showinfo("提示", f"请先选择一个{self.KIND_LABEL.get(self.kind, '项目')}",
                                parent=self.win)
        return it

    def open_folder(self):
        it = self._need()
        if not it:
            return
        d = it["path"] if os.path.isdir(it["path"]) else os.path.dirname(it["path"])
        try:
            os.startfile(d)
        except Exception as e:
            messagebox.showerror("打开失败", str(e), parent=self.win)

    def toggle_mod(self):
        """模组启用/禁用：.jar ↔ .jar.disabled。"""
        it = self._need()
        if not it:
            return
        src = it["path"]
        if it.get("enabled", True):
            dst = src + ".disabled"
        else:
            dst = src[:-len(".disabled")] if src.lower().endswith(".disabled") else src
        try:
            if os.path.exists(dst):
                messagebox.showerror("无法切换", f"目标文件已存在：\n{os.path.basename(dst)}",
                                     parent=self.win)
                return
            os.rename(src, dst)
        except Exception as e:
            messagebox.showerror("切换失败", str(e), parent=self.win)
            return
        self.win.refresh_all()

    def delete_item(self):
        it = self._need()
        if not it:
            return
        label = self.KIND_LABEL.get(self.kind, "项目")
        if not messagebox.askyesno(
                f"删除{label}",
                f"确定删除「{it.get('name')}」吗？\n\n{it['path']}\n\n"
                f"此操作不可恢复。", parent=self.win):
            return
        try:
            if os.path.isdir(it["path"]):
                shutil.rmtree(it["path"])
            else:
                os.remove(it["path"])
        except Exception as e:
            messagebox.showerror("删除失败", str(e), parent=self.win)
            return
        self.win.refresh_all()
