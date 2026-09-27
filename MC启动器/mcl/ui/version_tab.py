"""版本管理标签页：管理已安装版本。

- 列出本地已下载完整资源的版本
- 一键打开 模组 / 资源包 / 存档 / 数据包 / 游戏 文件夹
- 直接添加模组(.jar) 与 资源包(.zip) 到对应版本
- 删除不再需要的版本
"""
from __future__ import annotations
import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .. import paths, versions


def installed_versions() -> list[str]:
    """已安装版本 = 本地 versions 目录下存在 client.jar 的版本。"""
    out = []
    vd = paths.versions_dir()
    if not os.path.isdir(vd):
        return out
    for name in os.listdir(vd):
        if os.path.exists(os.path.join(vd, name, "client.jar")):
            out.append(name)
    out.sort(reverse=True)
    return out


class VersionTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self._build_toolbar()
        self._build_list()
        self._build_actions()
        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel"
                  ).pack(anchor="w", pady=(4, 0))
        self.refresh()

    # ---- 界面 ----
    def _build_toolbar(self):
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="刷新已安装版本", style="Accent.TButton",
                   command=self.refresh).pack(side="left")
        ttk.Button(row, text="查看详情", command=self.open_detail).pack(side="left", padx=6)
        ttk.Label(row, text="双击任一版本可查看其模组 / 资源包 / 存档 / 数据包",
                  style="Muted.TLabel").pack(side="left", padx=10)

    def _build_list(self):
        f = ttk.Frame(self, style="Card.TFrame")
        f.pack(fill="both", expand=True)
        cols = ("id", "type", "java", "size", "mods")
        self.tree = ttk.Treeview(f, columns=cols, show="headings")
        self.tree.heading("id", text="版本")
        self.tree.heading("type", text="类型")
        self.tree.heading("java", text="需要Java")
        self.tree.heading("size", text="客户端大小")
        self.tree.heading("mods", text="模组数")
        self.tree.column("id", width=220, anchor="w")
        self.tree.column("type", width=90, anchor="w")
        self.tree.column("java", width=80, anchor="w")
        self.tree.column("size", width=110, anchor="e")
        self.tree.column("mods", width=80, anchor="e")
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        vsb.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.tree.bind("<Double-1>", lambda e: self.open_detail())
        self.tree.bind("<Return>", lambda e: self.open_detail())

    def _build_actions(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(6, 0))
        for text, tip, cmd in [
            ("🔍 查看详情", "查看该版本的模组 / 资源包 / 存档 / 数据包列表", self.open_detail),
            ("📂 打开模组文件夹", "打开当前版本的 mods 目录", self.open_mods),
            ("🎨 打开资源包文件夹", "打开当前版本的 resourcepacks 目录", self.open_rp),
            ("🗺 打开存档文件夹", "打开当前版本的 saves 目录", self.open_saves),
            ("📦 打开数据包文件夹", "打开当前版本的 saves 目录(数据包位于各存档内)", self.open_dp),
            ("打开游戏目录", "打开当前版本的游戏根目录", self.open_game),
            ("➕ 添加模组", "选择 .jar 模组文件复制到当前版本", self.add_mods),
            ("🖼 添加资源包", "选择 .zip 资源包复制到当前版本", self.add_rp),
            ("🗑 删除版本", "删除当前版本的本地文件", self.delete_version),
        ]:
            b = ttk.Button(bar, text=text, command=cmd)
            b.pack(side="left", padx=2)
            widgets_tooltip(b, tip)

    # ---- 行为 ----
    def open_detail(self):
        """打开版本详情窗口：模组 / 资源包 / 存档 / 数据包。"""
        vid = self._need_version()
        if not vid:
            return
        try:
            from .version_detail import VersionDetailWindow
            VersionDetailWindow(self.winfo_toplevel(), vid)
        except Exception as e:
            messagebox.showerror("打开详情失败", str(e))

    def _selected(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _need_version(self) -> str | None:
        vid = self._selected()
        if not vid:
            messagebox.showinfo("提示", "请先在列表中选择一个版本")
        return vid

    def refresh(self):
        ids = installed_versions()
        self.tree.delete(*self.tree.get_children())
        for vid in ids:
            self.tree.insert("", "end", iid=vid, values=self._row(vid))
        if ids:
            self.tree.selection_set(ids[0])
        self._status_var.set(f"已安装 {len(ids)} 个版本（尚未下载的版本请到「下载中心」下载后再刷新）")

    def _row(self, vid):
        vdir = paths.version_dir(vid)
        # 类型 / 需要Java：读本地缓存的 version.json（不联网）
        vtype, jver = "未知", ""
        vjson_path = os.path.join(vdir, "version.json")
        if os.path.exists(vjson_path):
            try:
                with open(vjson_path, "r", encoding="utf-8") as f:
                    import json
                    vj = json.load(f)
                vtype = "正式版" if vj.get("type") == "release" else (
                    "快照" if vj.get("type") else "未知")
                mv = vj.get("javaVersion", {}).get("majorVersion")
                jver = f"Java {mv}" if mv else ""
            except Exception:
                pass
        client = os.path.join(vdir, "client.jar")
        size = f"{os.path.getsize(client) / 1e6:.1f} MB" if os.path.exists(client) else "-"
        mods_dir = os.path.join(paths.game_dir(vid), "mods")
        mods = len([f for f in os.listdir(mods_dir) if f.endswith(".jar")]) \
            if os.path.isdir(mods_dir) else 0
        return (vid, vtype, jver, size, str(mods))

    # 打开文件夹
    def _open_dir(self, path):
        os.makedirs(path, exist_ok=True)
        os.startfile(path)

    def open_mods(self):
        vid = self._need_version()
        if vid:
            self._open_dir(os.path.join(paths.game_dir(vid), "mods"))

    def open_rp(self):
        vid = self._need_version()
        if vid:
            self._open_dir(os.path.join(paths.game_dir(vid), "resourcepacks"))

    def open_saves(self):
        vid = self._need_version()
        if vid:
            self._open_dir(os.path.join(paths.game_dir(vid), "saves"))

    def open_dp(self):
        vid = self._need_version()
        if vid:
            self._open_dir(os.path.join(paths.game_dir(vid), "saves"))

    def open_game(self):
        vid = self._need_version()
        if vid:
            self._open_dir(paths.game_dir(vid))

    # 添加文件
    def _add_files(self, vid, sub, title, filetypes):
        files = filedialog.askopenfilenames(title=title, filetypes=filetypes)
        if not files:
            return
        target = os.path.join(paths.game_dir(vid), sub)
        os.makedirs(target, exist_ok=True)
        ok = 0
        for f in files:
            try:
                shutil.copy2(f, os.path.join(target, os.path.basename(f)))
                ok += 1
            except Exception as e:
                messagebox.showerror("复制失败", f"{os.path.basename(f)}:\n{e}")
        self.refresh()
        self._status_var.set(f"已向 {vid} 添加 {ok} 个文件到 {sub} 文件夹")

    def add_mods(self):
        vid = self._need_version()
        if vid:
            self._add_files(vid, "mods", "选择要添加的模组文件",
                            [("模组文件", "*.jar"), ("压缩包", "*.zip"), ("所有文件", "*.*")])

    def add_rp(self):
        vid = self._need_version()
        if vid:
            self._add_files(vid, "resourcepacks", "选择要添加的资源包",
                            [("资源包", "*.zip"), ("所有文件", "*.*")])

    def delete_version(self):
        vid = self._need_version()
        if not vid:
            return
        if not messagebox.askyesno("删除版本",
                                   f"确定要删除版本「{vid}」的全部本地文件吗？\n"
                                   f"（游戏存档与已装模组将一并删除，且不可恢复）"):
            return
        try:
            shutil.rmtree(paths.version_dir(vid))
        except Exception as e:
            messagebox.showerror("删除失败", str(e))
            return
        self.refresh()
        self._status_var.set(f"已删除版本 {vid}")


def widgets_tooltip(widget, text):
    try:
        from .widgets import ToolTip
        ToolTip(widget, text, delay=450)
    except Exception:
        pass
