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
from . import anim, bus, icons, navbar, theme, widgets

TYPE_LABELS = {"mod": "模组", "resourcepack": "资源包", "datapack": "数据包",
               "shader": "光影", "modpack": "整合包", "plugin": "插件"}
MISC_TYPES = [("shader", "光影"), ("modpack", "整合包"), ("plugin", "插件")]


class DownloadCenterTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=0)
        nb = ttk.Notebook(self)
        nb.add(GameDownloadPane(nb), text="  游戏本体  ")
        nb.add(ModDownloadPane(nb, "mod", "模组"), text="  模组  ")
        nb.add(ModDownloadPane(nb, "resourcepack", "资源包"), text="  资源包  ")
        nb.add(ModDownloadPane(nb, "datapack", "数据包"), text="  数据包  ")
        nb.add(ModDownloadPane(nb, "misc", "更多"), text="  更多  ")
        # 子页签：自绘导航条（选中态颜色渐变 + 指示条滑动），须先于 nb pack
        self.nav = navbar.NavTabs(self, nb)
        self.nav.pack(fill="x", padx=8, pady=(6, 2))
        nb.pack(fill="both", expand=True, padx=8)
        self.nb = nb


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
        super().__init__(master, padding=0)
        self.ptype = ptype          # 固定类型；misc 表示「更多」
        self.title = title
        self.misc_var = tk.StringVar(value="shader")
        self._current: dict | None = None
        self._results: list = []
        self._install_dir = ""
        self.custom_dir = ""
        self.target_var = tk.StringVar(value="客户端")
        self._hide_job = None
        self.loader = icons.IconLoader(64)
        self._build_filters()   # 顶部筛选行（唯一保留在列表上方的区域）
        self._build_results()   # 卡片网格：铺满筛选行以下全部空间
        self._build_install()   # 底部浮动条：仅任务进行时出现

    def _build_filters(self):
        """顶部筛选行：类型 / 加载器 / 版本 / 搜索框（列表铺满其下方）。"""
        f = tk.Frame(self, bg=theme.CARD, highlightthickness=1,
                     highlightbackground=theme.BORDER)
        f.pack(fill="x")
        row = tk.Frame(f, bg=theme.CARD)
        row.pack(fill="x", padx=12, pady=9)

        def lab(text):
            tk.Label(row, text=text, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.FONT_SMALL).pack(side="left")

        if self.ptype == "misc":
            lab("类型")
            self.type_box = ttk.Combobox(row, textvariable=self.misc_var,
                                         state="readonly", width=11,
                                         values=[f"{l} {k}" for k, l in MISC_TYPES])
            self.type_box.pack(side="left", padx=(4, 10))
            self.type_box.bind("<<ComboboxSelected>>", lambda e: self._on_type())

        lab("加载器")
        self.loader_var = tk.StringVar(value="全部")
        self.loader_box = ttk.Combobox(row, textvariable=self.loader_var,
                                       values=["全部"] + modrinth.LOADERS, width=9)
        self.loader_box.pack(side="left", padx=(4, 10))
        # 加载器仅对模组有意义；资源包/数据包/光影/整合包禁用
        if self._selected_type() not in ("mod", "plugin"):
            self.loader_box.configure(state="disabled")

        lab("版本")
        self.ver_var = tk.StringVar(value="1.21.1")
        self.ver_box = ttk.Combobox(row, textvariable=self.ver_var,
                                    values=["全部"] + modrinth.COMMON_VERSIONS, width=9)
        self.ver_box.pack(side="left", padx=(4, 12))

        self.query_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.query_var, width=28)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.do_search())
        self.search_btn = ttk.Button(row, text="搜索", style="Accent.TButton",
                                     command=self.do_search)
        self.search_btn.pack(side="left", padx=6)
        self.cn_query_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="中文搜索", variable=self.cn_query_var
                        ).pack(side="left", padx=(4, 0))

        ttk.Button(row, text="自定义目录…", command=self._pick_custom_dir
                   ).pack(side="right")
        self.custom_info = tk.Label(row, text="", bg=theme.CARD, fg=theme.MUTED,
                                    font=theme.FONT_SMALL)
        self.custom_info.pack(side="right", padx=10)

    def _build_results(self):
        """结果区：卡片网格铺满筛选行以下的所有空间。"""
        f = tk.Frame(self, bg=theme.BG)
        f.pack(fill="both", expand=True, pady=(8, 0))
        self.grid = widgets.CardGrid(f, card_w=ModCard.W, card_h=ModCard.H,
                                     bg=theme.BG)
        self.grid.pack(fill="both", expand=True)
        self.empty_lbl = tk.Label(f, text="输入关键词后点「搜索」，模组卡片会铺满这里",
                                  bg=theme.BG, fg=theme.MUTED, font=theme.FONT)
        self.empty_lbl.place(relx=0.5, rely=0.4, anchor="center")

    def _build_install(self):
        """底部浮动条：任务进行时才出现，平时不占列表空间。"""
        self.strip = tk.Frame(self, bg="#ffffff", highlightthickness=1,
                              highlightbackground=theme.BORDER)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.strip, textvariable=self.status_var, bg="#ffffff",
                 fg=theme.TEXT, font=theme.FONT_SMALL).pack(side="left", padx=(12, 8))
        self.progress = widgets.make_progress(self.strip)
        self.progress.pack(side="left", fill="x", expand=True, padx=4)
        self.open_btn = ttk.Button(self.strip, text="打开安装目录",
                                   command=self.open_dir)
        self.open_btn.pack(side="right", padx=10, pady=6)
        anim.bind_click(self.open_btn)
        self.info_var = tk.StringVar(value="未选择项目")

    # ---- 浮动条控制 ----
    def _show_strip(self, on: bool):
        if on:
            self.strip.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0, height=44)
            self.strip.tkraise()
        else:
            self.strip.place_forget()

    def _status(self, msg: str, auto_hide: bool = True, keep_ms: int = 4500):
        """更新状态并在底部浮动条显示；auto_hide 时若干秒后自动收起。"""
        self.status_var.set(msg)
        self._show_strip(True)
        if getattr(self, "_hide_job", None):
            try:
                self.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None
        if auto_hide:
            self._hide_job = self.after(keep_ms, lambda: self._show_strip(False))

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
        cn_flag = bool(self.cn_query_var.get())   # Tk 变量必须在主线程读取
        self._status(f"正在搜索{TYPE_LABELS.get(ptype, ptype)}…（Modrinth 较慢，请稍候）",
                     auto_hide=False)
        bus.run_async(lambda: self._do_search(q, ptype, version, loader, cn_flag),
                      "dl-search")

    def _do_search(self, q, ptype, version, loader, cn_flag=True):
        note = ""
        real_q = q
        # 中文关键词 -> 自动翻译成英文再搜
        if q and translate.has_chinese(q) and cn_flag:
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
        """把搜索结果渲染成铺满整页的卡片网格（含模组图标）。"""
        self.grid.clear()
        self._results = results
        for r in results:
            card = ModCard(self.grid.inner, r, self.loader,
                           on_open=self._open_detail, on_install=self.install_item)
            self.grid.add(card)
        if results:
            self.empty_lbl.place_forget()
        else:
            self.empty_lbl.configure(text="没有找到相关内容，换个关键词或放宽筛选试试")
            self.empty_lbl.place(relx=0.5, rely=0.4, anchor="center")
        self._status(f"「{q}」共找到 {len(results)} 个{TYPE_LABELS.get(ptype, ptype)}"
                     + (f"  {note}" if note else ""))

    def install_item(self, item: dict):
        """卡片上的「安装」按钮直接安装指定项目。"""
        self._current = {"project_id": item.get("project_id", ""),
                         "title": item.get("title", "")}
        self.install_selected()

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
                                           self._detail_install, self.loader)

    def _detail_install(self, item: dict):
        """详情页里的“下载并安装”：复用安装流程。"""
        self._current = {"project_id": item["project_id"], "title": item["title"]}
        self.install_selected()

    def install_selected(self):
        if not self._current:
            messagebox.showinfo("提示", "请先在结果中点击一个模组卡片")
            return
        pid = self._current["project_id"]
        version = self._cur_version()
        ptype = self._selected_type()
        loader = self._cur_loader(ptype)
        if not version:
            messagebox.showinfo("提示", "模组会按游戏版本自动安装到对应的 mods 文件夹，请先在筛选区选择具体游戏版本")
            return
        # Tk 变量一律在主线程读好再传进工作线程，避免 "main thread is not in main loop"
        ptype_ = ptype
        target = self.target_var.get().strip()
        custom = getattr(self, "custom_dir", "")
        self._status("获取版本列表…", auto_hide=False)
        bus.run_async(lambda: self._do_install(pid, version, loader, ptype_,
                                               target, custom), "dl-install")

    def _do_install(self, pid, version, loader, ptype="mod", target="客户端",
                    custom=""):
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
        self._install(f, version, ptype, target, custom)

    def _install(self, f, version, ptype="mod", target="客户端", custom=""):
        if target == "自定义" and custom:
            d = custom
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
        bus.dispatch(lambda: self._status(f"正在下载 {f['filename']} → {desc}…",
                                          auto_hide=False))
        widgets.set_progress(self.progress, 0, 1)

        def done():
            try:
                modrinth.install_file(f, d)
                bus.dispatch(lambda: (self._status(
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


# ============================================================
#  模组卡片：图标 + 名称 + 作者/下载量 + 一键安装
# ============================================================
class ModCard(tk.Frame):
    """一张模组卡片。整卡可点（打开详情），右下角按钮直接安装。"""

    W = 320          # 卡片基准宽度（网格会拉伸铺满列宽）
    H = 104
    PRESS_BG = "#e6ecff"
    HOVER_BG = "#f6f8ff"

    def __init__(self, master, item: dict, loader: "icons.IconLoader",
                 on_open, on_install):
        super().__init__(master, bg=theme.CARD, highlightthickness=1,
                         highlightbackground=theme.BORDER, cursor="hand2")
        self.configure(width=self.W, height=self.H)
        self.grid_propagate(False)
        self.item = item
        self._hover = False
        self._on_open = on_open

        icon = loader.cached(item.get("icon", "")) or loader.placeholder()
        self.icon_lbl = tk.Label(self, image=icon, bg=theme.CARD, cursor="hand2")
        self.icon_lbl.grid(row=0, column=0, rowspan=2, padx=12, pady=12, sticky="nw")
        if not loader.cached(item.get("icon", "")):
            loader.request(item.get("icon", ""), self._set_icon)

        info = tk.Frame(self, bg=theme.CARD, cursor="hand2")
        info.grid(row=0, column=1, sticky="nsew", pady=(12, 0))
        title = (item.get("title") or "(无名)").strip()
        t = tk.Label(info, text=title, bg=theme.CARD, fg=theme.TEXT,
                     font=theme.FONT_BOLD, anchor="w", justify="left",
                     wraplength=200, cursor="hand2")
        t.pack(fill="x")
        cn = translate.name_zh(title)
        if len(cn) > 24:
            cn = cn[:24] + "…"
        cn_lbl = tk.Label(info, text=cn, bg=theme.CARD, fg=theme.MUTED,
                          font=theme.FONT_SMALL, anchor="w", cursor="hand2")
        cn_lbl.pack(fill="x")
        meta = f"{item.get('author', '')} · 下载 {item.get('downloads', 0):,}"
        meta_lbl = tk.Label(info, text=meta, bg=theme.CARD, fg=theme.MUTED,
                            font=theme.FONT_SMALL, anchor="w", cursor="hand2")
        meta_lbl.pack(fill="x")

        self.install_btn = ttk.Button(self, text="安装", width=6,
                                      command=lambda: on_install(item))
        self.install_btn.grid(row=1, column=1, sticky="se", padx=12, pady=(0, 12))
        anim.bind_click(self.install_btn)
        self._img_ref = icon  # 防止被 GC

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # 整卡点击 -> 打开详情；按下瞬间整卡底色闪一下（点击动画）
        self._bg_widgets = [self, info, self.icon_lbl, t, cn_lbl, meta_lbl]
        for w in self._bg_widgets:
            w.bind("<Button-1>", self._click, add="+")
            w.bind("<Enter>", self._enter, add="+")
            w.bind("<Leave>", self._leave, add="+")
        widgets.ToolTip(self, f"{title}\n点击查看详情，右下角可直接安装")

    def _set_icon(self, img):
        if not self.winfo_exists():
            return
        self._img_ref = img
        self.icon_lbl.configure(image=img)

    # ---- 悬停 / 按下 ----
    def _enter(self, _e=None):
        self._hover = True
        self._paint(self.HOVER_BG, theme.PRIMARY)

    def _leave(self, _e=None):
        self._hover = False
        self._paint(theme.CARD, theme.BORDER)

    def _click(self, _e=None):
        self._paint(self.PRESS_BG, theme.PRIMARY)
        self.after(anim.PRESS_MS, self._restore)
        try:
            self._on_open(self.item)
        except Exception:
            pass

    def _restore(self):
        if self._hover:
            self._paint(self.HOVER_BG, theme.PRIMARY)
        else:
            self._paint(theme.CARD, theme.BORDER)

    def _paint(self, bg: str, bd: str):
        """统一刷新卡片底色与描边（卡片本体 + 内部所有子控件）。"""
        for w in self._bg_widgets:
            try:
                w.configure(bg=bg)
            except Exception:
                pass
        try:
            self.configure(highlightbackground=bd)
        except Exception:
            pass


class ModDetailWindow(tk.Toplevel):
    """模组详情页：完整介绍 + 翻译 + 下载安装 + 跳转 MC百科 / Modrinth。"""

    SEG = {"mod": "mod", "resourcepack": "resourcepack", "datapack": "datapack",
           "shader": "shader", "modpack": "modpack", "plugin": "plugin"}

    def __init__(self, master, item: dict, ptype: str, version: str, loader: str,
                 on_install, icon_loader=None):
        super().__init__(master)
        self._title = item.get("title", "模组详情")
        self._slug = item.get("slug", "")
        self._ptype = ptype
        self._desc = item.get("description", "") or ""
        self._icon_img = None
        self.title(self._title)
        self.geometry("820x620")
        self.minsize(700, 520)
        self.configure(bg="#ffffff")

        # 头部：模组图标 + 标题 + 元信息
        head = ttk.Frame(self)
        head.pack(fill="x", padx=16, pady=(14, 4))
        if icon_loader is not None:
            url = item.get("icon", "")
            img = icon_loader.cached(url) or icon_loader.placeholder()
            self._icon_img = img
            self.icon_lbl = tk.Label(head, image=img, bg="#ffffff")
            self.icon_lbl.pack(side="left", padx=(0, 14))
            if not icon_loader.cached(url):
                icon_loader.request(url, self._set_icon)
        txt = ttk.Frame(head)
        txt.pack(side="left", fill="x", expand=True)
        ttk.Label(txt, text=self._title, font=("Microsoft YaHei UI", 15, "bold")
                  ).pack(anchor="w")
        ttk.Label(txt, text=f"作者: {item.get('author', '')}    下载量: {item.get('downloads', 0):,}",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Label(txt, text=f"类型: {TYPE_LABELS.get(ptype, ptype)}    游戏版本: {version or '不限'}    加载器: {loader or '不限'}",
                  style="Muted.TLabel").pack(anchor="w")

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

        # 三级页签：自绘导航条（须在所有页 add 完之后创建，且先于 nb pack）
        navbar.NavTabs(right, nb, bg="#ffffff").pack(fill="x", padx=2, pady=(0, 2))
        nb.pack(fill="both", expand=True)

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
        # 详情页内的按钮也带点击动画
        anim.bind_click_all(self)

    def _set_icon(self, img):
        if not self.winfo_exists():
            return
        self._icon_img = img
        try:
            self.icon_lbl.configure(image=img)
        except Exception:
            pass

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

