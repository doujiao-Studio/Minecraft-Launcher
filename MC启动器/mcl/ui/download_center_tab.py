"""下载中心：五个子页。

  ├── 游戏本体        —— 浏览/下载 Minecraft 各版本客户端
  ├── 模组            —— Modrinth 搜索并安装模组
  ├── 资源包          —— Modrinth 搜索并安装资源包
  ├── 数据包          —— Modrinth 搜索并安装数据包
  └── 更多            —— 光影 / 整合包 / 插件
"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .. import launch, modrinth, network, paths, translate, versions
from . import bus, widgets

TYPE_LABELS = {"mod": "模组", "resourcepack": "资源包", "datapack": "数据包",
               "shader": "光影", "modpack": "整合包", "plugin": "插件"}
MISC_TYPES = [("shader", "光影"), ("modpack", "整合包"), ("plugin", "插件")]


class DownloadCenterTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        nb.add(GameDownloadPane(nb), text="  游戏本体  ")
        nb.add(ModDownloadPane(nb, "mod", "模组"), text="  模组  ")
        nb.add(ModDownloadPane(nb, "resourcepack", "资源包"), text="  资源包  ")
        nb.add(ModDownloadPane(nb, "datapack", "数据包"), text="  数据包  ")
        nb.add(ModDownloadPane(nb, "misc", "更多"), text="  更多  ")


# ============================================================
#  子页一：游戏本体下载
# ============================================================
class GameDownloadPane(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self._build_toolbar()
        self._build_list()
        self._build_progress()
        self.refresh_versions()

    def _build_toolbar(self):
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="刷新版本清单", style="Accent.TButton",
                   command=self.refresh_versions).pack(side="left")
        ttk.Button(row, text="下载选中版本", command=self.download).pack(side="left", padx=6)
        ttk.Button(row, text="打开版本目录", command=self.open_dir).pack(side="left")
        ttk.Label(row, text="提示: 下载后到「启动器」页选择同一版本即可启动",
                  style="Muted.TLabel").pack(side="left", padx=14)

    def _build_list(self):
        f = ttk.Frame(self, style="Card.TFrame")
        f.pack(fill="both", expand=True)
        cols = ("id", "type", "time")
        self.tree = ttk.Treeview(f, columns=cols, show="headings")
        self.tree.heading("id", text="版本")
        self.tree.heading("type", text="类型")
        self.tree.heading("time", text="发布时间")
        self.tree.column("id", width=220, anchor="w")
        self.tree.column("type", width=100, anchor="w")
        self.tree.column("time", width=200, anchor="w")
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        vsb.pack(side="right", fill="y", padx=(0, 8), pady=8)

    def _build_progress(self):
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status_var, style="Primary.TLabel"
                  ).pack(anchor="w", pady=(6, 0))
        self.progress = widgets.make_progress(self)
        self.progress.pack(fill="x", pady=(2, 0))

    def refresh_versions(self):
        self.status_var.set("正在拉取版本清单…")
        bus.run_async(self._do_refresh, "game-versions")

    def _do_refresh(self):
        try:
            man = versions.fetch_version_manifest()
        except network.DownloadError as e:
            bus.dispatch(lambda: (self.status_var.set(f"刷新失败: {e}"),
                                  messagebox.showerror("刷新失败", str(e))))
            return
        self._man = man
        bus.dispatch(lambda: self._fill(man))

    def _fill(self, man):
        self.tree.delete(*self.tree.get_children())
        for v in man:
            t = "正式版" if v.type == "release" else "快照"
            self.tree.insert("", "end", iid=v.id,
                             values=(v.id, t, v.time[:10] if v.time else ""))
        self.status_var.set(f"共 {len(man)} 个版本")

    def _selected_version(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def download(self):
        vid = self._selected_version()
        if not vid:
            messagebox.showinfo("提示", "请先在列表中选中一个版本再下载")
            return
        self.status_var.set(f"开始下载 {vid} 的客户端资源…")
        bus.run_async(lambda: self._do_download(vid), "game-download")

    def _do_download(self, vid):
        def prog(stage, done, total):
            bus.dispatch(lambda: self.status_var.set(f"{stage}  {int(done)}/{int(total)}"))
            widgets.set_progress(self.progress, done, total)
        try:
            launch.download_client(vid, progress=prog)
            bus.dispatch(lambda: (self.status_var.set(f"{vid} 下载完成，可去「启动器」页启动"),
                                  widgets.set_progress(self.progress, 1, 1)))
        except network.DownloadError as e:
            bus.dispatch(lambda: messagebox.showerror("下载失败", str(e)))
        except Exception as e:
            bus.dispatch(lambda: messagebox.showerror("下载失败", f"{e}"))

    def open_dir(self):
        vid = self._selected_version()
        if not vid:
            messagebox.showinfo("提示", "请先在列表中选中一个版本，再点「打开版本目录」")
            return
        d = paths.version_dir(vid)
        os.makedirs(d, exist_ok=True)
        os.startfile(d)


# ============================================================
#  子页：模组 / 资源包 / 数据包 / 更多（Modrinth）
# ============================================================
class ModDownloadPane(ttk.Frame):
    """固定类型的搜索下载页。ptype 为 None 时显示「更多」类型选择。"""

    def __init__(self, master, ptype: str | None = None, title: str = ""):
        super().__init__(master, padding=8)
        self.ptype = ptype          # 固定类型；misc 表示「更多」
        self.title = title
        self.misc_var = tk.StringVar(value="shader")
        self._current: dict | None = None
        self._results: list = []
        self._install_dir = ""
        self._build_filters()
        self._build_results()
        self._build_install()

    def _build_filters(self):
        f = ttk.LabelFrame(self, text="搜索")
        f.pack(fill="x")

        row1 = ttk.Frame(f)
        row1.pack(fill="x", padx=4, pady=4)

        if self.ptype == "misc":
            # 更多：光影/整合包/插件
            ttk.Label(row1, text="类型:").pack(side="left")
            self.type_box = ttk.Combobox(row1, textvariable=self.misc_var,
                                         state="readonly",
                                         values=[f"{l} {k}" for k, l in MISC_TYPES],
                                         width=12)
            self.type_box.pack(side="left", padx=4)
            self.type_box.bind("<<ComboboxSelected>>", lambda e: self._on_type())
        else:
            pass

        ttk.Label(row1, text="加载器:").pack(side="left")
        self.loader_var = tk.StringVar(value="全部")
        self.loader_box = ttk.Combobox(row1, textvariable=self.loader_var,
                                       values=["全部"] + modrinth.LOADERS, width=10)
        self.loader_box.pack(side="left", padx=4)
        # 加载器仅对模组有意义；资源包/数据包/光影/整合包禁用
        if self._selected_type() not in ("mod", "plugin"):
            self.loader_box.configure(state="disabled")

        ttk.Label(row1, text="游戏版本:").pack(side="left")
        self.ver_var = tk.StringVar(value="1.21.1")
        self.ver_box = ttk.Combobox(row1, textvariable=self.ver_var,
                                    values=["全部"] + modrinth.COMMON_VERSIONS, width=9)
        self.ver_box.pack(side="left", padx=4)

        # 下载位置：默认客户端；可通过“下载到自定义位置”改
        self.target_var = tk.StringVar(value="客户端")
        self.custom_dir = ""

        row2 = ttk.Frame(f)
        row2.pack(fill="x", padx=4, pady=(0, 6))
        self.query_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.query_var, width=36).pack(side="left", padx=4)
        ttk.Button(row2, text="搜索", style="Accent.TButton",
                   command=self.do_search).pack(side="left")
        self.cn_query_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="中文搜索(自动翻译)", variable=self.cn_query_var
                        ).pack(side="left", padx=(10, 2))
        self.dp_label = ttk.Label(row2, text="", style="Muted.TLabel")
        self.dp_label.pack(side="left", padx=6)

    def _build_results(self):
        label = TYPE_LABELS.get(self._selected_type(), self.title)
        f = ttk.LabelFrame(self, text=f"{label}搜索结果（双击即可下载安装）")
        f.pack(fill="both", expand=True, pady=(6, 0))
        cols = ("title", "title_cn")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=12)
        self.tree.heading("title", text="模组名称")
        self.tree.heading("title_cn", text="名称翻译")
        self.tree.column("title", width=200, anchor="w")
        self.tree.column("title_cn", width=260, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._open_detail_from_sel())
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", pady=4)

    def _build_install(self):
        f = ttk.Frame(self)
        f.pack(fill="x", pady=(6, 0))
        self.info_var = tk.StringVar(value="未选择项目")
        ttk.Label(f, textvariable=self.info_var).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="下载并安装所选", style="Accent.TButton",
                   command=self.install_selected).pack(side="left")
        ttk.Button(row, text="下载到自定义位置…", command=self._pick_custom_dir
                   ).pack(side="left", padx=4)
        ttk.Button(row, text="打开安装目录", command=self.open_dir
                   ).pack(side="left", padx=4)
        self.custom_info = ttk.Label(f, text="", style="Muted.TLabel")
        self.custom_info.pack(anchor="w")
        self.progress = widgets.make_progress(f)
        self.progress.pack(fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(f, textvariable=self.status_var, style="Primary.TLabel"
                  ).pack(anchor="w", pady=(2, 0))

    # ---- 行为 ----
    def _selected_type(self) -> str:
        if self.ptype == "misc":
            raw = self.misc_var.get()
            return raw.split(" ")[0] if raw else "shader"
        return self.ptype or "mod"

    def _on_type(self):
        pass

    def _pick_custom_dir(self):
        d = filedialog.askdirectory(title="选择自定义下载位置")
        if d:
            self.custom_dir = d
            self.target_var.set("自定义")
            if hasattr(self, "custom_info"):
                self.custom_info.config(text=f"将下载到: {d}")
        else:
            self.target_var.set("客户端")
            if hasattr(self, "custom_info"):
                self.custom_info.config(text="")

    def _cur_version(self):
        v = self.ver_var.get().strip()
        return "" if v == "全部" else v

    def _cur_loader(self, ptype=None):
        pt = ptype or self._selected_type()
        if pt not in ("mod", "plugin"):
            return ""
        l = self.loader_var.get().strip()
        return "" if l == "全部" else l

    def do_search(self):
        q = self.query_var.get().strip()
        ptype = self._selected_type()
        version = self._cur_version()
        loader = self._cur_loader(ptype)
        self.status_var.set(f"正在搜索{TYPE_LABELS.get(ptype, ptype)}…（Modrinth 较慢，请稍候）")
        bus.run_async(lambda: self._do_search(q, ptype, version, loader), "dl-search")

    def _do_search(self, q, ptype, version, loader):
        note = ""
        real_q = q
        # 中文关键词 -> 自动翻译成英文再搜
        if q and translate.has_chinese(q) and self.cn_query_var.get():
            real_q = translate.to_english(q)
            if real_q and real_q != q:
                note = f"已把「{q}」译为「{real_q}」搜索"
        try:
            results = modrinth.search_projects(real_q, ptype=ptype, version=version,
                                               loader=loader, limit=40)
        except modrinth.ModrinthError as e:
            bus.dispatch(lambda: messagebox.showerror("搜索失败", str(e)))
            return
        bus.dispatch(lambda: self._fill_results(results, real_q, ptype, note))

    def _fill_results(self, results, q, ptype, note=""):
        self.tree.delete(*self.tree.get_children())
        self._results = results
        for r in results:
            title = r["title"] or ""
            cn = translate.name_zh(title)  # 本地即时翻译，无网络
            if len(cn) > 26:
                cn = cn[:26] + "…"
            self.tree.insert("", "end", iid=r["project_id"], values=(title, cn))
        self.status_var.set(f"「{q}」共找到 {len(results)} 个{TYPE_LABELS.get(ptype, ptype)}"
                            + (f"  {note}" if note else ""))

    def _on_select(self, _e):
        sel = self.tree.selection()
        if not sel:
            return
        item = self.tree.item(sel[0])
        self._current = {"project_id": sel[0], "title": item["values"][0]}
        self.info_var.set(f"已选: {item['values'][0]}  (作者 {item['values'][1]})")
        self._open_detail_from_sel()

    def _open_detail_from_sel(self):
        sel = self.tree.selection()
        if not sel:
            return
        pid = sel[0]
        for r in self._results:
            if r["project_id"] == pid:
                self._open_detail(r)
                break

    def _open_detail(self, r: dict):
        """打开模组详情页；若同一模组详情已打开则置前。"""
        if (getattr(self, "_detail_win", None)
                and self._detail_win.winfo_exists()):
            self._detail_win.lift()
            self._detail_win.focus_set()
            return
        ptype = self._selected_type()
        version = self._cur_version()
        loader = self._cur_loader(ptype)
        self._detail_win = ModDetailWindow(self, r, ptype, version, loader,
                                           self._detail_install)

    def _detail_install(self, item: dict):
        """详情页里的“下载并安装”：复用安装流程。"""
        self._current = {"project_id": item["project_id"], "title": item["title"]}
        self.install_selected()

    def install_selected(self):
        if not self._current:
            messagebox.showinfo("提示", "请先在结果中选择一个项目（可双击）")
            return
        pid = self._current["project_id"]
        version = self._cur_version()
        ptype = self._selected_type()
        loader = self._cur_loader(ptype)
        if not version:
            messagebox.showinfo("提示", "模组会按游戏版本自动安装到对应的 mods 文件夹，请先在筛选区选择具体游戏版本")
            return
        self.status_var.set("获取版本列表…")
        bus.run_async(lambda: self._do_install(pid, version, loader), "dl-install")

    def _do_install(self, pid, version, loader):
        try:
            vers = modrinth.get_versions(pid, version=version, loader=loader)
        except modrinth.ModrinthError as e:
            bus.dispatch(lambda: messagebox.showerror("获取版本失败", str(e)))
            return
        if not vers:
            bus.dispatch(lambda: messagebox.showinfo(
                "无匹配版本", f"该项目没有 {version}{'/'+loader if loader else ''} 的版本"))
            return
        f = modrinth.best_file(vers[0])
        if not f:
            bus.dispatch(lambda: messagebox.showerror("无文件", "该项目没有可下载文件"))
            return
        self._install(f, version)

    def _install(self, f, version):
        ptype = self._selected_type()
        if self.target_var.get().strip() == "自定义" and getattr(self, "custom_dir", ""):
            d = self.custom_dir
            desc = d
            try:
                os.makedirs(d, exist_ok=True)
            except Exception as e:
                bus.dispatch(lambda: messagebox.showerror("路径错误", str(e)))
                return
        else:
            try:
                d, desc = modrinth.install_target_dir("client", "", ptype, version)
            except Exception as e:
                bus.dispatch(lambda: messagebox.showerror("路径错误", str(e)))
                return
        self._install_dir = d
        bus.dispatch(lambda: self.status_var.set(f"正在下载 {f['filename']} → {desc}…"))
        widgets.set_progress(self.progress, 0, 1)

        def done():
            try:
                modrinth.install_file(f, d)
                bus.dispatch(lambda: (self.status_var.set(
                    f"安装完成: {f['filename']} → {desc}"),
                    widgets.set_progress(self.progress, 1, 1)))
            except modrinth.ModrinthError as e:
                bus.dispatch(lambda: messagebox.showerror("下载失败", str(e)))

        bus.run_async(done, "dl-download")

    def open_dir(self):
        d = self._install_dir
        if not d or not os.path.isdir(d):
            messagebox.showinfo("提示", "还没有安装目录，先下载一个文件")
            return
        os.startfile(d)



class ModDetailWindow(tk.Toplevel):
    """模组详情页：完整介绍 + 翻译 + 下载安装 + 跳转 MC百科 / Modrinth。"""

    SEG = {"mod": "mod", "resourcepack": "resourcepack", "datapack": "datapack",
           "shader": "shader", "modpack": "modpack", "plugin": "plugin"}

    def __init__(self, master, item: dict, ptype: str, version: str, loader: str,
                 on_install):
        super().__init__(master)
        self._title = item.get("title", "模组详情")
        self._slug = item.get("slug", "")
        self._ptype = ptype
        self._desc = item.get("description", "") or ""
        self.title(self._title)
        self.geometry("820x620")
        self.minsize(700, 520)
        self.configure(bg="#ffffff")

        ttk.Label(self, text=self._title, font=("Microsoft YaHei UI", 15, "bold")
                  ).pack(anchor="w", padx=16, pady=(14, 2))
        ttk.Label(self, text=f"作者: {item.get('author', '')}    下载量: {item.get('downloads', 0):,}",
                  style="Muted.TLabel").pack(anchor="w", padx=16)
        ttk.Label(self, text=f"类型: {TYPE_LABELS.get(ptype, ptype)}    游戏版本: {version or '不限'}    加载器: {loader or '不限'}",
                  style="Muted.TLabel").pack(anchor="w", padx=16, pady=2)

        # 左右分栏：左=模组介绍，右=版本列表
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=16, pady=(8, 0))

        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text="模组介绍:").pack(anchor="w", pady=(0, 2))
        df = ttk.Frame(left)
        df.pack(fill="both", expand=True)
        self.desc_txt = tk.Text(df, wrap="word", height=16, width=52,
                                font=("Microsoft YaHei UI", 10),
                                bg="#f6f7fb", relief="flat")
        self.desc_txt.pack(fill="both", expand=True)
        self.desc_txt.insert("1.0", self._desc or "（该模组暂无简介）")
        self.desc_txt.configure(state="disabled")
        self.translated = False

        row = ttk.Frame(left)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="翻译简介(中)", command=self._translate_desc
                   ).pack(side="left")
        ttk.Button(row, text="恢复原文", command=self._restore_desc
                   ).pack(side="left", padx=4)
        ttk.Button(row, text="刷新版本", command=self._load_versions_async
                   ).pack(side="left", padx=4)

        # 支持的版本 / 更新记录（右侧）
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)

        gf = ttk.Frame(nb)
        nb.add(gf, text="可用版本")
        gf_row = ttk.Frame(gf)
        gf_row.pack(fill="both", expand=True, padx=4, pady=4)
        self.gv_list = tk.Listbox(gf_row, height=6, font=("Microsoft YaHei UI", 10))
        gv_sb = ttk.Scrollbar(gf_row, orient="vertical", command=self.gv_list.yview)
        self.gv_list.configure(yscrollcommand=gv_sb.set)
        gv_sb.pack(side="right", fill="y")
        self.gv_list.pack(side="left", fill="both", expand=True)
        self.gv_list.insert("end", "加载中…")

        uf = ttk.Frame(nb)
        nb.add(uf, text="更新记录")
        ucols = ("ver", "date", "gv", "loader")
        self.up_tree = ttk.Treeview(uf, columns=ucols, show="headings", height=9)
        self.up_tree.heading("ver", text="版本")
        self.up_tree.heading("date", text="日期")
        self.up_tree.heading("gv", text="游戏版本")
        self.up_tree.heading("loader", text="加载器")
        self.up_tree.column("ver", width=110, anchor="w")
        self.up_tree.column("date", width=92, anchor="w")
        self.up_tree.column("gv", width=150, anchor="w")
        self.up_tree.column("loader", width=90, anchor="w")
        self.up_tree.pack(fill="both", expand=True, padx=4, pady=4)

        # 后台拉取该模组的全部版本
        self._pid = item.get("project_id", "")
        self._version = version or ""
        self._load_versions_async()

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=16, pady=10)
        ttk.Button(btns, text="下载并安装", style="Accent.TButton",
                   command=lambda: on_install(item)).pack(side="left")
        ttk.Button(btns, text="在 MC百科查看", command=self._open_mcmod
                   ).pack(side="left", padx=6)
        ttk.Button(btns, text="Modrinth 页面", command=self._open_modrinth
                   ).pack(side="left")

    def _set_desc(self, txt: str):
        self.desc_txt.configure(state="normal")
        self.desc_txt.delete("1.0", "end")
        self.desc_txt.insert("1.0", txt or "（无简介）")
        self.desc_txt.configure(state="disabled")

    def _translate_desc(self):
        def do():
            zh = translate.translate(self._desc, to_zh=True)
            if zh and zh != self._desc:
                bus.dispatch(lambda: self._set_desc(zh))
        self.status_ok("正在翻译…")
        bus.run_async(do, "detail-translate")

    def status_ok(self, msg: str):
        pass

    def _restore_desc(self):
        self._set_desc(self._desc)


    # ---- 支持的版本 / 更新记录 ----
    @staticmethod
    def _ver_key(name):
        import re
        return [int(x) if x.isdigit() else x.lower()
                for x in re.split(r"([0-9]+)", str(name))]

    def _load_versions_async(self):
        if not self._pid:
            return
        self.gv_list.delete(0, "end")
        self.gv_list.insert("end", "加载中…")
        self.up_tree.delete(*self.up_tree.get_children())
        bus.run_async(lambda: self._load_versions(self._pid), "detail-versions")

    def _load_versions(self, pid):
        try:
            vers = modrinth.get_versions(pid)
        except Exception as e:
            bus.dispatch(lambda: self._show_versions_error(str(e)))
            return
        vers.sort(key=lambda v: v.get("date", "") or "", reverse=True)
        if self._version:
            cur = [v for v in vers if self._version in v.get("game_versions", [])]
        else:
            cur = vers
        bus.dispatch(lambda: self._fill_versions(vers, cur))

    def _fill_versions(self, all_rows, cur_rows):
        self.gv_list.delete(0, "end")
        groups: dict = {}
        for v in all_rows:
            vn = v.get("version_number", "")
            if not vn:
                continue
            for g in v.get("game_versions", []):
                groups.setdefault(g, []).append(vn)
        if not groups:
            self.gv_list.insert("end", "（暂无可用模组版本）")
        for mc in sorted(groups, key=self._ver_key, reverse=True):
            self.gv_list.insert("end", f"━━━━ {mc} ━━━━")
            self.gv_list.itemconfig("end", fg="#7a7f8a")
            seen = set()
            for vn in groups[mc]:
                if vn not in seen:
                    seen.add(vn)
                    self.gv_list.insert("end", f"    {vn}")
        self.up_tree.delete(*self.up_tree.get_children())
        for v in (cur_rows if cur_rows else all_rows)[:60]:
            self.up_tree.insert("", "end", values=(
                v.get("version_number", ""),
                (v.get("date", "") or "")[:10],
                ", ".join(v.get("game_versions", [])[:3]),
                ", ".join(v.get("loaders", []))))

    def _show_versions_error(self, msg):
        self.gv_list.delete(0, "end")
        self.gv_list.insert("end", f"加载失败: {msg}")
        self.gv_list.insert("end", "（点右上角「刷新版本」可重试）")

    def _open_mcmod(self):
        import webbrowser
        import urllib.parse
        url = "https://www.mcmod.cn/s?key=" + urllib.parse.quote(self._title)
        webbrowser.open(url)

    def _open_modrinth(self):
        import webbrowser
        if not self._slug:
            return
        seg = self.SEG.get(self._ptype, "mod")
        webbrowser.open(f"https://modrinth.com/{seg}/{self._slug}")

