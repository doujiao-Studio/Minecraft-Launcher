"""隧道标签页：局域网直连 / 自建中继隧道 / 免费 SSH 隧道。"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from .. import config, paths, servermgr
from ..tunnel import lan, relay
from . import bus, widgets


class TunnelTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.client: relay.TunnelClient | None = None
        self.method = tk.StringVar(value="relay")
        self._build_methods()
        self._build_lan()
        self._build_relay()
        self._build_external()
        self._build_status()

    def _build_methods(self):
        f = ttk.LabelFrame(self, text="穿透方式")
        f.pack(fill="x")
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=4)
        for label, val in (("局域网直连（同 WiFi）", "lan"),
                           ("自建中继隧道（无公网IP方案）", "relay"),
                           ("免费 SSH 隧道", "external")):
            ttk.Radiobutton(row, text=label, variable=self.method, value=val
                            ).pack(side="left", padx=6)
        ttk.Label(f, text="本地服务器端口:").pack(side="left", padx=(12, 2))
        self.local_port = ttk.Entry(f, width=8)
        self.local_port.insert(0, str(config.get("server_port", 25565)))
        self.local_port.pack(side="left")

    def _build_lan(self):
        self.lan_frame = ttk.LabelFrame(self, text="局域网直连")
        self.lan_frame.pack(fill="x", pady=(6, 0))
        self.lan_label = ttk.Label(self.lan_frame, text="点击「检测」获取本机局域网地址")
        self.lan_label.pack(anchor="w", padx=6, pady=4)
        ttk.Button(self.lan_frame, text="检测局域网地址", command=self.check_lan
                   ).pack(anchor="w", padx=6, pady=(0, 6))

    def _build_relay(self):
        f = ttk.LabelFrame(self, text="自建中继隧道")
        f.pack(fill="x", pady=(6, 0))
        grid = ttk.Frame(f)
        grid.pack(fill="x", padx=6, pady=4)
        self.r_host = tk.StringVar(value=config.get("relay_host", ""))
        self.r_ctrl = tk.StringVar(value=str(config.get("relay_control_port", 6000)))
        self.r_token = tk.StringVar(value=config.get("relay_token", ""))
        self.r_remote = tk.StringVar(value=str(config.get("relay_remote_port", 25565)))
        ttk.Label(grid, text="中继地址:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(grid, textvariable=self.r_host, width=24).grid(row=0, column=1, pady=2)
        ttk.Label(grid, text="控制端口:").grid(row=0, column=2, sticky="e", padx=4, pady=2)
        ttk.Entry(grid, textvariable=self.r_ctrl, width=7).grid(row=0, column=3, pady=2)
        ttk.Label(grid, text="密钥:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(grid, textvariable=self.r_token, width=24).grid(row=1, column=1, pady=2)
        ttk.Label(grid, text="映射端口:").grid(row=1, column=2, sticky="e", padx=4, pady=2)
        ttk.Entry(grid, textvariable=self.r_remote, width=7).grid(row=1, column=3, pady=2)
        btns = ttk.Frame(f)
        btns.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Button(btns, text="启动隧道", command=self.start_relay).pack(side="left")
        ttk.Button(btns, text="停止隧道", command=self.stop_relay).pack(side="left", padx=4)
        ttk.Button(btns, text="复制中继服务端启动命令", command=self.copy_relay_cmd
                   ).pack(side="left", padx=4)
        ttk.Button(btns, text="中继说明", command=self.show_relay_help).pack(side="left", padx=4)

    def _build_external(self):
        f = ttk.LabelFrame(self, text="免费 SSH 隧道（无需自建服务器）")
        f.pack(fill="x", pady=(6, 0))
        self.ext_cmd = tk.StringVar(
            value="ssh -R 25565:localhost:25565 free.localhost.run")
        ttk.Entry(f, textvariable=self.ext_cmd, width=60).pack(fill="x", padx=6, pady=4)
        btns = ttk.Frame(f)
        btns.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Button(btns, text="复制命令", command=self.copy_ext).pack(side="left")
        ttk.Label(btns, text="（需本机装有 ssh，Windows 10+ 自带）").pack(side="left", padx=6)

    def _build_status(self):
        f = ttk.LabelFrame(self, text="隧道状态")
        f.pack(fill="both", expand=True, pady=(6, 0))
        self.tconsole = widgets.Console(f, height=12)
        self.tconsole.pack(fill="both", expand=True, padx=4, pady=4)

    # ---- 行为 ----
    def check_lan(self):
        port = int(self.local_port.get() or 25565)
        ips = lan.get_local_ips()
        lines = []
        for ip in ips:
            ok = lan.probe_port(ip, port)
            lines.append(f"{ip}:{port}  {'● 在线' if ok else '○ 未监听'}")
        self.lan_label.configure(text="\n".join(lines))

    def _save_relay_fields(self):
        config.set("relay_host", self.r_host.get().strip())
        config.set("relay_control_port", int(self.r_ctrl.get() or 6000))
        config.set("relay_token", self.r_token.get().strip())
        config.set("relay_remote_port", int(self.r_remote.get() or 25565))

    def start_relay(self):
        self._save_relay_fields()
        host = config.get("relay_host", "").strip()
        if not host:
            messagebox.showinfo("提示", "请先填写中继服务器地址\n（需要一台有公网 IP 的机器运行中继服务端）")
            return
        self.client = relay.TunnelClient(
            host, config.get("relay_control_port", 6000), config.get("relay_token", ""),
            target_host="127.0.0.1", target_port=int(self.local_port.get() or 25565),
            on_status=self.tconsole.append, on_data=self.tconsole.append)
        self.client.start()

    def stop_relay(self):
        if self.client:
            self.client.stop()
            self.client = None

    def copy_relay_cmd(self):
        host = self.r_host.get().strip() or "你的公网IP"
        token = self.r_token.get().strip() or "mcl"
        cmd = (f'& "D:\\python 3.15.0rc2\\python.exe" -m mcl.tunnel.relay_server '
               f'--control-port 6000 --token {token} --public-host {host}')
        self._clip(cmd)
        self.tconsole.append(f"[MCL] 在公网机器上运行：\n  {cmd}")

    def show_relay_help(self):
        msg = (
            "【自建中继服务器怎么做】\n"
            "1. 找一台有公网 IP 的机器（免费云主机、同学/朋友的公网主机都行）；\n"
            "2. 在上面也安装 Python，把本程序目录拷过去，运行：\n"
            f"   python -m mcl.tunnel.relay_server --token {self.r_token.get() or 'mcl'} --public-host 你的IP\n"
            "3. 在本地这里填上那台机器的地址、控制端口(6000)、相同密钥，点「启动隧道」；\n"
            "4. 把「中继公网地址:映射端口」发给好友，他们即可加入你的服务器。\n\n"
            "原理：中继负责在公网开放一个端口并转发，本地只需向外发起连接即可，"
            "所以没有公网 IP 也能开服。"
        )
        messagebox.showinfo("自建中继服务器", msg)

    def copy_ext(self):
        self._clip(self.ext_cmd.get())
        self.tconsole.append("[MCL] 已复制免费隧道命令，请在本机终端运行。")

    def _clip(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass
