"""账户管理对话框：离线 / Microsoft 正版（设备码）/ 外置登录（Yggdrasil）。"""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

from .. import accounts, config
from . import bus, theme, widgets


class AccountDialog(tk.Toplevel):
    def __init__(self, master, on_changed=None, initial_tab: str | None = None):
        super().__init__(master)
        self.title("账户管理")
        self.geometry("580x560")
        self.minsize(520, 480)
        self.transient(master)
        self.on_changed = on_changed
        self._stop = threading.Event()
        self._ygg_profiles: list[dict] = []
        self._ygg_payload: dict = {}
        self._device_code: dict = {}

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        self._build_offline(nb)
        self._build_msa(nb)
        self._build_ygg(nb)
        self._build_list()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bar, text="关闭", command=self.close).pack(side="right")

        # initial_tab 用于「正版登录」按钮直达对应页签
        tab_index = {"offline": 0, "msa": 1, "microsoft": 1, "ygg": 2}.get(
            (initial_tab or "").lower())
        if tab_index is not None:
            try:
                nb.select(tab_index)
            except Exception:
                pass
        self.refresh_list()
        self.protocol("WM_DELETE_WINDOW", self.close)
        try:
            self.grab_set()
        except Exception:
            pass

    # ------------------------------------------------------------ 离线
    def _build_offline(self, nb):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="  离线  ")
        ttk.Label(f, text="离线模式：不改服务器设置也能进自建服，但无法进入开启正版验证的服务器。",
                  wraplength=520, justify="left").pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(12, 0))
        ttk.Label(row, text="游戏名:").pack(side="left")
        self.off_var = tk.StringVar(value=config.get("user_name", "Steve"))
        ttk.Entry(row, textvariable=self.off_var, width=18).pack(side="left", padx=4)
        ttk.Button(row, text="使用离线模式", style="Accent.TButton",
                   command=self._use_offline).pack(side="left", padx=8)
        ttk.Label(f, text="提示：正版/外置登录后，游戏名由账户决定，这里不能再手动改。",
                  style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

    def _use_offline(self):
        name = (self.off_var.get() or "Steve").strip() or "Steve"
        config.set("user_name", name)
        accounts.logout()
        self.refresh_list()
        self._notify()
        messagebox.showinfo("已切换", f"当前使用离线模式：{name}", parent=self)

    # ------------------------------------------------------------ Microsoft
    def _build_msa(self, nb):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="  正版登录 (Microsoft)  ")
        ttk.Label(f, text="1. 点「开始登录」   2. 在打开的网页里输入下方代码   3. 同意授权后自动完成",
                  wraplength=520, justify="left").pack(anchor="w")

        self.msa_status = tk.StringVar(value="未登录")
        ttk.Label(f, textvariable=self.msa_status, style="Muted.TLabel").pack(
            anchor="w", pady=(6, 0))

        # 设备码展示区（获取后才显示内容）
        self.code_box = ttk.LabelFrame(f, text=" 登录码 ")
        self.code_var = tk.StringVar(value="")
        tk.Label(self.code_box, textvariable=self.code_var, font=("Consolas", 26, "bold"),
                 fg=theme.PRIMARY, bg=theme.CARD).pack(pady=(6, 2))
        self.uri_var = tk.StringVar(value="")
        ttk.Label(self.code_box, textvariable=self.uri_var).pack()
        brow = ttk.Frame(self.code_box)
        brow.pack(pady=6)
        ttk.Button(brow, text="打开授权网页", command=self._open_uri).pack(side="left", padx=4)
        ttk.Button(brow, text="复制代码", command=self._copy_code).pack(side="left", padx=4)
        self.code_box.pack_forget()

        brow2 = ttk.Frame(f)
        brow2.pack(fill="x", pady=(10, 0))
        self.msa_btn = ttk.Button(brow2, text="开始登录", style="Accent.TButton",
                                  command=self._msa_start)
        self.msa_btn.pack(side="left")
        ttk.Button(brow2, text="取消", command=self._msa_cancel).pack(side="left", padx=6)

        ttk.Label(f, text="登录码有效期约 15 分钟。内置客户端 ID 来自开源项目 picomc；"
                          "若失效，可在「设置 → 账户」换成自己在 Azure 申请的客户端 ID。",
                  style="Muted.TLabel", wraplength=520).pack(anchor="w", pady=(10, 0))

    def _msa_start(self):
        self._stop.clear()
        self.msa_btn.configure(state="disabled", text="登录中…")
        self.msa_status.set("正在获取登录码…")
        bus.run_async(self._msa_worker, "msa-login")

    def _msa_cancel(self):
        self._stop.set()
        self.msa_btn.configure(state="normal", text="开始登录")
        self.msa_status.set("已取消")
        self.code_box.pack_forget()

    def _msa_worker(self):
        try:
            dc = accounts.msa_begin()
            self._device_code = dc
            bus.dispatch(lambda: self._show_code(dc))
            self.msa_status_set("等待你在网页里完成授权…")
            ms = accounts.msa_poll(dc.get("device_code", ""),
                                   dc.get("client_id", accounts.client_id()),
                                   interval=int(dc.get("interval", 5) or 5),
                                   expires_in=int(dc.get("expires_in", 900) or 900),
                                   should_stop=self._stop.is_set)
            self.msa_status_set("正在兑换 Minecraft 令牌…")
            acc = accounts.msa_finish(ms)
            accounts.add_account(acc)
            bus.dispatch(lambda: self._login_ok(acc))
        except Exception as e:
            bus.dispatch(lambda e=e: self._login_fail(e))

    def msa_status_set(self, text):
        bus.dispatch(lambda: self.msa_status.set(text))

    def _show_code(self, dc):
        self.code_var.set(dc.get("user_code", ""))
        uri = dc.get("verification_uri") or "https://www.microsoft.com/link"
        self.uri_var.set(uri)
        self.code_box.pack(fill="x", pady=(8, 0))
        try:
            webbrowser.open(uri)
        except Exception:
            pass
        self.msa_status.set("已打开浏览器，请输入上面的登录码")

    def _open_uri(self):
        uri = self.uri_var.get() or "https://www.microsoft.com/link"
        try:
            webbrowser.open(uri)
        except Exception:
            pass

    def _copy_code(self):
        code = self.code_var.get()
        if not code:
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        self.msa_status.set(f"已复制 {code}，粘贴到网页即可")

    def _login_ok(self, acc):
        self.msa_btn.configure(state="normal", text="开始登录")
        self.code_box.pack_forget()
        self.msa_status.set(f"已登录：{acc.name}")
        self.refresh_list()
        self._notify()
        messagebox.showinfo("登录成功",
                            f"已登录正版账户：{acc.name}\n现在可以进入开启正版验证的服务器。",
                            parent=self)

    def _login_fail(self, e):
        self.msa_btn.configure(state="normal", text="开始登录")
        self.msa_status.set("登录失败")
        messagebox.showerror("登录失败", str(e), parent=self)

    # ------------------------------------------------------------ 外置登录
    def _build_ygg(self, nb):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="  外置登录  ")
        ttk.Label(f, text="适用于 Blessing Skin / authlib-injector 一类皮肤站，"
                          "填认证地址 + 账号密码。",
                  wraplength=520, justify="left").pack(anchor="w")

        grid = ttk.Frame(f)
        grid.pack(fill="x", pady=(10, 0))
        self.ygg_url = tk.StringVar(value=config.get("ygg_url", ""))
        self.ygg_user = tk.StringVar()
        self.ygg_pass = tk.StringVar()
        ttk.Label(grid, text="认证地址:").grid(row=0, column=0, sticky="e", pady=4)
        ttk.Entry(grid, textvariable=self.ygg_url, width=42).grid(row=0, column=1, pady=4)
        ttk.Label(grid, text="账号:").grid(row=1, column=0, sticky="e", pady=4)
        ttk.Entry(grid, textvariable=self.ygg_user, width=24).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(grid, text="密码:").grid(row=2, column=0, sticky="e", pady=4)
        ttk.Entry(grid, textvariable=self.ygg_pass, width=24, show="*").grid(
            row=2, column=1, sticky="w", pady=4)

        brow = ttk.Frame(f)
        brow.pack(fill="x", pady=(8, 0))
        self.ygg_btn = ttk.Button(brow, text="登录", style="Accent.TButton",
                                  command=self._ygg_start)
        self.ygg_btn.pack(side="left")
        self.ygg_status = tk.StringVar(value="")
        ttk.Label(brow, textvariable=self.ygg_status, style="Muted.TLabel").pack(
            side="left", padx=8)

        # 多角色选择（默认隐藏）
        self.prof_box = ttk.Frame(f)
        ttk.Label(self.prof_box, text="该账号有多个角色，请选择:").pack(side="left")
        self.prof_var = tk.StringVar()
        self.prof_cb = ttk.Combobox(self.prof_box, textvariable=self.prof_var,
                                    width=20, state="readonly")
        self.prof_cb.pack(side="left", padx=4)
        ttk.Button(self.prof_box, text="使用这个角色",
                   command=self._ygg_use_profile).pack(side="left", padx=4)

    def _ygg_start(self):
        url = self.ygg_url.get().strip()
        user = self.ygg_user.get().strip()
        pwd = self.ygg_pass.get()
        if not url or not user or not pwd:
            messagebox.showwarning("缺少信息", "请填写认证地址、账号和密码", parent=self)
            return
        config.set("ygg_url", url)
        self.ygg_btn.configure(state="disabled")
        self.ygg_status.set("正在登录…")
        bus.run_async(lambda: self._ygg_worker(url, user, pwd), "ygg-login")

    def _ygg_worker(self, url, user, pwd):
        try:
            payload, profiles = accounts.ygg_authenticate(url, user, pwd)
            if len(profiles) == 1:
                acc = accounts.ygg_account(url, payload, profiles[0])
                accounts.add_account(acc)
                bus.dispatch(lambda: self._login_ok(acc))
                return
            self._ygg_profiles = profiles
            self._ygg_payload = payload
            bus.dispatch(self._show_profile_chooser)
        except Exception as e:
            bus.dispatch(lambda e=e: self._login_fail(e))

    def _show_profile_chooser(self):
        names = [p.get("name", "?") for p in self._ygg_profiles]
        self.prof_cb["values"] = names
        if names:
            self.prof_cb.set(names[0])
        self.prof_box.pack(fill="x", pady=(8, 0))
        self.ygg_btn.configure(state="normal")
        self.ygg_status.set("请选择要使用的角色")

    def _ygg_use_profile(self):
        name = self.prof_var.get()
        prof = next((p for p in self._ygg_profiles if p.get("name") == name), None)
        if not prof:
            return
        acc = accounts.ygg_account(self.ygg_url.get().strip(), self._ygg_payload, prof)
        accounts.add_account(acc)
        self.prof_box.pack_forget()
        self._login_ok(acc)

    # ------------------------------------------------------------ 账户列表
    def _build_list(self):
        box = ttk.LabelFrame(self, text=" 已保存的账户 ")
        box.pack(fill="both", expand=True, padx=10, pady=(4, 0))
        cols = ("name", "mode", "state")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=5)
        for c, t, w in (("name", "账户", 200), ("mode", "类型", 130), ("state", "状态", 120)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sb = ttk.Scrollbar(box, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=8, padx=(0, 8))

        btns = ttk.Frame(box)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="设为当前", command=self._set_current).pack(side="left")
        ttk.Button(btns, text="删除", command=self._remove).pack(side="left", padx=6)
        ttk.Button(btns, text="退出登录(回离线)", command=self._logout).pack(side="left")

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        cur = accounts.active_index()
        for i, a in enumerate(accounts.list_accounts()):
            state = "当前使用" if i == cur else ""
            if a.mode != accounts.OFFLINE:
                state = (state + " / " if state else "") + (
                    "令牌已过期" if a.expired else "有效")
            self.tree.insert("", "end", iid=f"acc-{i}",
                             values=(a.name, a.mode_label, state))

    def _sel_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0].split("-")[1])
        except Exception:
            return None

    def _set_current(self):
        i = self._sel_index()
        if i is None:
            return
        accounts.set_active(i)
        self.refresh_list()
        self._notify()

    def _remove(self):
        i = self._sel_index()
        if i is None:
            return
        if not messagebox.askyesno("删除", "确定删除这个账户？", parent=self):
            return
        accounts.remove_account(i)
        self.refresh_list()
        self._notify()

    def _logout(self):
        accounts.logout()
        self.refresh_list()
        self._notify()

    # ------------------------------------------------------------ 收尾
    def _notify(self):
        if self.on_changed:
            try:
                self.on_changed()
            except Exception:
                pass

    def close(self):
        self._stop.set()
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
