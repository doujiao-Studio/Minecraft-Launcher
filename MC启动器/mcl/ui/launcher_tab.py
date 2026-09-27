"""启动器标签页：左侧已下载版本列表 + 右侧操作区/账户/进度 + 游戏控制台。"""
from __future__ import annotations
import os
import re
import tkinter as tk
from tkinter import ttk, messagebox

from .. import accounts, config, java, launch, paths, versions
from . import bus, theme, widgets


class LauncherTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.game: launch.GameProcess | None = None

        self._build_top()
        self._build_console()
        self._sync_account()
        # 初始显示本地已下载版本
        self._do_refresh()

    # ---- 界面 ----
    def _build_top(self):
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True)

        # 左：已下载版本列表
        left = ttk.LabelFrame(main, text=" 已下载版本 ")
        left.pack(side="left", fill="y", padx=(0, 8))
        self.ver_list = tk.Listbox(left, width=24, height=16, activestyle="none",
                                   selectmode="browse",
                                   font=("Microsoft YaHei UI", 10),
                                   bg="#ffffff", fg=theme.TEXT,
                                   selectbackground=theme.PRIMARY,
                                   selectforeground="#ffffff",
                                   highlightthickness=1,
                                   highlightbackground=theme.BORDER,
                                   highlightcolor=theme.PRIMARY,
                                   bd=0, relief="flat")
        self.ver_list.pack(fill="both", expand=True, padx=6, pady=6)
        sb = ttk.Scrollbar(left, command=self.ver_list.yview)
        self.ver_list.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=6, padx=(0, 6))
        self.ver_list.bind("<<ListboxSelect>>", lambda e: self._select_version())
        ttk.Button(left, text="刷新版本", command=self.refresh_versions).pack(
            fill="x", padx=6, pady=(0, 6))

        # 右：操作区 + 账户 + 进度 + 控制台
        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True)
        self._right = right

        ops = ttk.Frame(right)
        ops.pack(fill="x")
        self.launch_btn = ttk.Button(ops, text="▶ 启动游戏", style="Accent.TButton",
                                     command=self.launch_game)
        self.launch_btn.pack(side="left", padx=2)
        self.stop_btn = ttk.Button(ops, text="■ 停止", style="Danger.TButton",
                                   command=self.stop_game)
        self.stop_btn.pack(side="left", padx=6)
        self.open_btn = ttk.Button(ops, text="打开目录", command=self.open_game_dir)
        self.open_btn.pack(side="left", padx=2)
        widgets.ToolTip(self.launch_btn, "下载缺失资源并启动选中的游戏版本")
        widgets.ToolTip(self.stop_btn, "强制结束游戏进程")
        widgets.ToolTip(self.open_btn, "打开该版本的游戏目录（存档/模组）")

        # 第一行：游戏名 + JVM + Java
        row1 = ttk.Frame(right)
        row1.pack(fill="x", pady=(6, 0))
        ttk.Label(row1, text="游戏名:").pack(side="left")
        self.name_var = tk.StringVar(value=config.get("user_name", "Steve"))
        self.name_entry = ttk.Entry(row1, textvariable=self.name_var, width=16)
        self.name_entry.pack(side="left", padx=4)
        ttk.Label(row1, text="JVM:").pack(side="left")
        self.jvm_label = ttk.Label(row1, text=config.get("jvm_args", ""))
        self.jvm_label.pack(side="left", padx=4)
        ttk.Label(row1, text="Java:").pack(side="left")
        self.java_label = ttk.Label(row1, text=self._java_desc())
        self.java_label.pack(side="left", padx=4)

        # 第二行：账户区（独立一行，正版登录入口一眼可见，不与上面的信息抢宽度）
        acc = ttk.LabelFrame(right, text=" 账户 ")
        acc.pack(fill="x", pady=(8, 0))
        ttk.Label(acc, text="当前:").pack(side="left", padx=(6, 0), pady=6)
        self.acc_var = tk.StringVar(value=accounts.active_label())
        self.acc_label = tk.Label(acc, textvariable=self.acc_var,
                                  fg=theme.PRIMARY, bg=theme.CARD,
                                  font=("Microsoft YaHei UI", 9, "bold"))
        self.acc_label.pack(side="left", padx=(2, 10), pady=6)
        self.msa_btn = ttk.Button(acc, text="正版登录 (Microsoft)",
                                  style="Accent.TButton",
                                  command=lambda: self.open_accounts("msa"))
        self.msa_btn.pack(side="left", pady=6)
        ttk.Button(acc, text="账户管理", command=self.open_accounts).pack(
            side="left", padx=6, pady=6)
        ttk.Button(acc, text="退出登录", command=self.logout_account).pack(
            side="right", padx=8, pady=6)

        self.progress = widgets.make_progress(right)
        self.progress.pack(fill="x", pady=(6, 0))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(right, textvariable=self.status_var, style="Muted.TLabel").pack(
            anchor="w", pady=(2, 0))

    def _build_console(self):
        con = ttk.LabelFrame(self._right, text="游戏控制台")
        con.pack(fill="both", expand=True, pady=(6, 0))
        self.console = widgets.Console(con, height=16)
        self.console.pack(fill="both", expand=True)
        self.console.on_command(self.send_game)

    def _java_desc(self) -> str:
        jp = java.effective_java()
        if not jp:
            return "未设置"
        maj = java.java_major(jp)
        return f"{os.path.basename(jp)} (Java {maj})"

    # ---- 账户 ----
    def open_accounts(self, tab=None):
        """tab=None 打开完整管理；传 "msa" 直达正版登录页。"""
        from .account import AccountDialog
        AccountDialog(self.winfo_toplevel(), on_changed=self._sync_account,
                      initial_tab=tab)

    def logout_account(self):
        accounts.logout()
        self._sync_account()

    def _sync_account(self):
        """把界面同步到当前账户：登录态下游戏名只读。"""
        a = accounts.active()
        self.acc_var.set(accounts.active_label())
        self.name_var.set(a.name)
        try:
            self.name_entry.configure(
                state="normal" if a.mode == accounts.OFFLINE else "disabled")
            self.msa_btn.configure(
                text="重新登录" if a.mode != accounts.OFFLINE else "正版登录 (Microsoft)")
        except Exception:
            pass

    # ---- 已下载版本 ----
    @staticmethod
    def _ver_key(name):
        return [int(x) if x.isdigit() else x.lower()
                for x in re.split(r"([0-9]+)", name)]

    def _downloaded_versions(self):
        out = []
        vd = paths.versions_dir()
        try:
            for name in os.listdir(vd):
                if name.startswith(".") or name in ("game", "__pycache__"):
                    continue
                if os.path.isdir(os.path.join(vd, name)):
                    out.append(name)
        except Exception:
            pass
        out.sort(key=self._ver_key)
        return out

    def refresh_versions(self):
        self._do_refresh()

    def _do_refresh(self):
        ids = self._downloaded_versions()
        self._fill_versions(ids)
        if not ids:
            self.status_var.set("暂无已下载版本，请到「下载中心」下载游戏")

    def _fill_versions(self, ids):
        self.ver_list.delete(0, "end")
        for vid in ids:
            self.ver_list.insert("end", vid)
        cur = config.get("last_version", "")
        if cur in ids:
            i = ids.index(cur)
            self.ver_list.selection_clear(0, "end")
            self.ver_list.selection_set(i)
            self.ver_list.see(i)
        elif ids:
            self.ver_list.selection_set(0)
        self.status_var.set(f"共 {len(ids)} 个已下载版本")

    # ---- 版本选择 ----
    def selected_version(self) -> str:
        sel = self.ver_list.curselection()
        if sel:
            return self.ver_list.get(sel[0])
        return config.get("last_version", "")

    def _select_version(self):
        sel = self.ver_list.curselection()
        if sel:
            config.set("last_version", self.ver_list.get(sel[0]))

    # ---- 加载锁 ----
    def _set_loading(self, loading: bool):
        """加载期间禁用操作按钮，禁止取消。"""
        st = "disabled" if loading else "normal"
        for b in (self.launch_btn, self.stop_btn, self.open_btn):
            try:
                b.configure(state=st)
            except Exception:
                pass
        if loading:
            self.status_var.set("正在加载游戏…（加载期间不可取消）")

    # ---- 行为 ----
    def launch_game(self):
        vid = self.selected_version()
        if not vid:
            messagebox.showinfo("提示", "请先选择版本")
            return
        # 只有离线模式才允许手动改游戏名
        if accounts.active().mode == accounts.OFFLINE:
            config.set("user_name", self.name_var.get() or "Steve")
        self._set_loading(True)
        bus.run_async(lambda: self._do_launch(vid), "launch")

    def _do_launch(self, vid):
        try:
            self.console.append(f"[NCL] 正在准备启动 {vid} …")

            # 先确保登录态有效（正版令牌约 24 小时过期，可自动续期）
            try:
                acc = accounts.active()
                if acc.mode != accounts.OFFLINE and acc.expired:
                    self.console.append("[NCL] 登录令牌已过期，正在自动续期…")
                    accounts.ensure_valid(acc)
                    bus.dispatch(self._sync_account)
                    self.console.append("[NCL] 令牌续期成功")
            except Exception as e:
                bus.dispatch(lambda e=e: messagebox.showerror(
                    "登录已过期", f"{e}\n\n请到「账户管理」里重新登录。"))
                return

            # 先检查 Java 是否满足版本要求
            try:
                vjson = versions.parse_version_json(vid)
                required = versions.required_java(vjson)
            except Exception:
                required = None
            if required and not java.select_java_path(required):
                best = java.highest_java()
                best_major = java.java_major(best) if best else 0
                msg = (f"版本 {vid} 需要 Java {required}，但本机最高只有 Java {best_major}"
                       f"（{best or '未找到'}）。\n\n"
                       f"请安装 Java {required} 或更高版本，"
                       f"或在「下载中心」选择更低的 MC 版本（如 1.16.5 需要 Java 17）。")
                self.console.append("[NCL] 中止启动：Java 版本不足，未开始下载")
                bus.dispatch(lambda: messagebox.showerror("启动失败", msg))
                return

            def prog(stage, done, total):
                bus.dispatch(lambda: self.status_var.set(f"{stage}  {int(done)}/{int(total)}"))
                widgets.set_progress(self.progress, done, total)

            try:
                launch.download_client(vid, progress=prog)
            except Exception as e:
                bus.dispatch(lambda e=e: messagebox.showerror("启动失败", f"资源下载失败:\n{e}"))
                return
            try:
                cmd = launch.build_launch_command(vid)
            except Exception as e:
                bus.dispatch(lambda e=e: messagebox.showerror("启动失败", str(e)))
                return
            self.console.append("[NCL] 资源就绪，拉起游戏进程…")
            self.game = launch.GameProcess(cmd, self.console.append,
                                           on_exit=lambda c: self.console.append(
                                               f"[NCL] 游戏已退出 (code {c})"))
            try:
                self.game.start()
            except Exception as e:
                bus.dispatch(lambda e=e: messagebox.showerror("启动失败", str(e)))
                return
        finally:
            bus.dispatch(lambda: self._set_loading(False))

    def stop_game(self):
        if self.game:
            self.game.stop(force=True)

    def send_game(self, text: str):
        if self.game:
            self.game.send(text)

    def open_game_dir(self):
        vid = self.selected_version()
        if not vid:
            return
        d = paths.game_dir(vid)
        os.startfile(d)
