"""服务器标签页：创建服务器、启停、控制台、配置、白名单、备份。"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, messagebox

from .. import config, network, paths, servermgr, versions
from . import bus, navbar, widgets


class ServerTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.proc = None
        self._build_create()
        self._build_control()
        self._build_tabs()
        self.refresh_list()

    def _build_create(self):
        f = ttk.LabelFrame(self, text="创建服务器")
        f.pack(fill="x")
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="名称:").pack(side="left")
        self.sname = ttk.Entry(row, width=14)
        self.sname.pack(side="left", padx=4)
        ttk.Label(row, text="类型:").pack(side="left")
        self.stype = ttk.Combobox(row, values=servermgr.server_types(), width=10,
                                  state="readonly")
        self.stype.set("vanilla")
        self.stype.pack(side="left", padx=4)
        ttk.Label(row, text="MC版本:").pack(side="left")
        self.sver = ttk.Combobox(row, width=14)
        self.sver.pack(side="left", padx=4)
        ttk.Button(row, text="创建", command=self.create_server).pack(side="left", padx=6)
        self.create_status = ttk.Label(f, text="")
        self.create_status.pack(anchor="w", padx=6, pady=(0, 4))
        bus.run_async(self._load_versions, "srv-versions")

    def _load_versions(self):
        try:
            man = versions.fetch_version_manifest()
        except network.DownloadError:
            return
        ids = [v.id for v in man if v.type in ("release", "snapshot")][:40]
        bus.dispatch(lambda: self.sver.configure(values=ids) or (
            self.sver.set(ids[0]) if ids else None))

    def _build_control(self):
        f = ttk.LabelFrame(self, text="运行控制")
        f.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="服务器:").pack(side="left")
        self.sel_box = ttk.Combobox(row, width=18, state="readonly")
        self.sel_box.pack(side="left", padx=4)
        self.sel_box.bind("<<ComboboxSelected>>", lambda e: self._load_props())
        ttk.Button(row, text="启动", command=self.start_server).pack(side="left", padx=2)
        ttk.Button(row, text="停止", command=self.stop_server).pack(side="left", padx=2)
        ttk.Button(row, text="备份", command=self.backup).pack(side="left", padx=2)
        ttk.Button(row, text="打开目录", command=self.open_dir).pack(side="left", padx=2)
        self.state_label = ttk.Label(f, text="状态: 未选择")
        self.state_label.pack(anchor="w", padx=6, pady=(0, 4))

        con = ttk.LabelFrame(self, text="服务器控制台")
        con.pack(fill="both", expand=True, pady=(6, 0))
        self.console = widgets.Console(con, height=10)
        self.console.pack(fill="both", expand=True)
        inp = ttk.Frame(con)
        inp.pack(fill="x", pady=2)
        self.cmd_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.cmd_var).pack(side="left", fill="x", expand=True)
        ttk.Button(inp, text="发送", command=self.send_cmd).pack(side="left", padx=4)

    def _build_tabs(self):
        nb = ttk.Notebook(self)
        self._build_props(nb)
        self._build_players(nb)
        self._build_backups(nb)
        # 子页签：自绘导航条（选中态颜色渐变 + 指示条滑动），须先于 nb pack
        navbar.NavTabs(self, nb).pack(fill="x", padx=8, pady=(6, 2))
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 0))

    def _build_props(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="服务器配置")
        grid = ttk.Frame(f)
        grid.pack(fill="x")
        rows = [("端口", "server_port"), ("MOTD", "motd"), ("游戏模式", "gamemode"),
                ("难度", "difficulty"), ("最大玩家", "max_players"),
                ("视距", "view_distance")]
        self.prop_vars = {}
        for i, (label, key) in enumerate(rows):
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky="w", padx=4, pady=2)
            v = tk.StringVar()
            self.prop_vars[key] = v
            ttk.Entry(grid, textvariable=v, width=30).grid(row=i, column=1, sticky="w", pady=2)
        self.online_var = tk.BooleanVar()
        ttk.Checkbutton(grid, text="正版验证 (online-mode)", variable=self.online_var
                        ).grid(row=len(rows), column=1, sticky="w", pady=2)
        ttk.Button(f, text="保存配置到服务器", command=self.save_props).pack(anchor="w", pady=6)

    def _build_players(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="白名单 / OP")
        sub = ttk.Frame(f)
        sub.pack(fill="x")
        self.whitelist_txt = tk.Text(sub, height=8)
        self.whitelist_txt.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.ops_txt = tk.Text(sub, height=8)
        self.ops_txt.pack(side="left", fill="both", expand=True)
        ttk.Label(f, text="每行一个玩家名（白名单  |  OP）").pack(anchor="w")
        ttk.Button(f, text="保存名单", command=self.save_players).pack(anchor="w", pady=4)

    def _build_backups(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="备份")
        self.backup_list = tk.Listbox(f, height=8)
        self.backup_list.pack(fill="both", expand=True)
        ttk.Button(f, text="刷新列表", command=self.refresh_backups).pack(anchor="w", pady=4)
        ttk.Button(f, text="打开备份文件夹", command=self.open_backup_dir).pack(anchor="w")

    # ---- 行为 ----
    def refresh_list(self):
        servers = servermgr.list_servers()
        self.sel_box["values"] = servers
        if servers and not self.sel_box.get():
            self.sel_box.set(servers[0])
            self._load_props()
        self.refresh_backups()

    def create_server(self):
        name = self.sname.get().strip()
        if not name:
            messagebox.showinfo("提示", "请输入服务器名称")
            return
        if servermgr.is_created(name):
            messagebox.showinfo("提示", "该服务器已存在，请直接选择")
            return
        vtype = self.stype.get()
        vid = self.sver.get()
        if not vid:
            messagebox.showinfo("提示", "请选择 MC 版本")
            return

        def do():
            # 工作线程不能直接操作 Tk 控件，统一投递回主线程
            bus.dispatch(lambda: self.create_status.configure(
                text=f"正在创建 {name} ({vtype} {vid}) …"))
            try:
                servermgr.create_server(name, vtype, vid,
                                        progress=lambda s, p: bus.dispatch(
                                            lambda: self.create_status.configure(text=s)))
                bus.dispatch(lambda: (self.create_status.configure(text="创建完成"),
                                      self.refresh_list()))
            except Exception as e:
                bus.dispatch(lambda: self.create_status.configure(text=f"创建失败: {e}"))

        bus.run_async(do, "create-server")

    def _selected(self) -> str | None:
        name = self.sel_box.get()
        return name if name else None

    def start_server(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("提示", "请先选择服务器")
            return
        if servermgr.is_running(name):
            return
        try:
            servermgr.start(name, self.console.append,
                            on_exit=lambda c: self._on_exit(name, c))
            self.state_label.configure(text=f"状态: 运行中 ({name})")
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    def _on_exit(self, name, code):
        bus.dispatch(lambda: self.console.append(f"[服务器] {name} 已停止 (code {code})"))
        bus.dispatch(lambda: self.state_label.configure(text=f"状态: 已停止 ({name})"))

    def stop_server(self):
        name = self._selected()
        if not name:
            return
        self.console.append(f"[NCL] 发送停止命令到 {name} …")
        bus.run_async(lambda: servermgr.stop(name), "stop-server")

    def send_cmd(self):
        name = self._selected()
        if not name or not self.cmd_var.get():
            return
        servermgr.send_command(name, self.cmd_var.get())
        self.cmd_var.set("")

    def _load_props(self):
        name = self._selected()
        if not name:
            return
        p = servermgr.read_props(name)
        for key, var in self.prop_vars.items():
            var.set(p.get(_key_map()[key], config.get(key, "")))
        self.online_var.set(p.get("online-mode", "false") == "true")
        self._load_players(name)

    def _load_players(self, name):
        w = "\n".join(servermgr.read_player_list(name, "whitelist"))
        o = "\n".join(servermgr.read_player_list(name, "ops"))
        self.whitelist_txt.delete("1.0", "end")
        self.whitelist_txt.insert("1.0", w)
        self.ops_txt.delete("1.0", "end")
        self.ops_txt.insert("1.0", o)

    def save_props(self):
        name = self._selected()
        if not name:
            return
        p = servermgr.read_props(name)
        for key, var in self.prop_vars.items():
            if key in p:
                p[key] = var.get()
            else:
                p[_key_map()[key]] = var.get()
        p["online-mode"] = "true" if self.online_var.get() else "false"
        servermgr.write_props(name, p)
        self.console.append(f"[NCL] 已保存 {name} 的配置")

    def save_players(self):
        name = self._selected()
        if not name:
            return
        w = [x.strip() for x in self.whitelist_txt.get("1.0", "end").splitlines() if x.strip()]
        o = [x.strip() for x in self.ops_txt.get("1.0", "end").splitlines() if x.strip()]
        servermgr.write_player_list(name, "whitelist", w)
        servermgr.write_player_list(name, "ops", o)
        self.console.append(f"[NCL] 已保存 {name} 的名单")

    def backup(self):
        name = self._selected()
        if not name:
            return
        bus.run_async(lambda: self._do_backup(name), "backup")

    def _do_backup(self, name):
        try:
            dest = servermgr.backup(name)
            bus.dispatch(lambda: (self.console.append(f"[NCL] 备份完成: {dest}"),
                                  self.refresh_backups()))
        except Exception as e:
            bus.dispatch(lambda: messagebox.showerror("备份失败", str(e)))

    def refresh_backups(self):
        name = self._selected()
        if not name:
            return
        self.backup_list.delete(0, "end")
        for b in servermgr.list_backups(name):
            self.backup_list.insert("end", os.path.basename(b))

    def open_dir(self):
        name = self._selected()
        if name:
            os.startfile(paths.server_dir(name))

    def open_backup_dir(self):
        d = os.path.join(paths.base_dir(), "backups")
        os.makedirs(d, exist_ok=True)
        os.startfile(d)


def _key_map() -> dict:
    return {"server_port": "server-port", "motd": "motd", "gamemode": "gamemode",
            "difficulty": "difficulty", "max_players": "max-players",
            "view_distance": "view-distance"}
