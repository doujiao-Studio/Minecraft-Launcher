"""设置标签页：Java、JVM、分辨率、服务器默认值、镜像源。"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import config, java
from . import bus


class SettingsTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=0)
        from .widgets import ScrollableFrame
        self.scroll = ScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)
        self._build_java()
        self._build_game()
        self._build_server()
        self._build_misc()

    def _build_java(self):
        f = ttk.LabelFrame(self, text="Java 环境")
        f.pack(in_=self.scroll.inner, fill="x", pady=(0, 6))
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=4)
        self.java_var = tk.StringVar(value=config.get("java_path", ""))
        ttk.Label(row, text="java.exe:").pack(side="left")
        ttk.Entry(row, textvariable=self.java_var, width=44).pack(side="left", padx=4)
        ttk.Button(row, text="浏览", command=self.browse_java).pack(side="left")
        ttk.Button(row, text="自动检测", command=self.auto_java).pack(side="left", padx=4)
        self.java_info = ttk.Label(f, text="")
        self.java_info.pack(anchor="w", padx=6, pady=(0, 4))

        row2 = ttk.Frame(f)
        row2.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(row2, text="JVM 参数(客户端):").pack(side="left")
        self.jvm_var = tk.StringVar(value=config.get("jvm_args", ""))
        ttk.Entry(row2, textvariable=self.jvm_var, width=40).pack(side="left", padx=4)
        ttk.Label(row2, text="JVM 参数(服务器):").pack(side="left")
        self.sjvm_var = tk.StringVar(value=config.get("server_jvm_args", "-Xmx2G"))
        ttk.Entry(row2, textvariable=self.sjvm_var, width=18).pack(side="left", padx=4)

    def _build_game(self):
        f = ttk.LabelFrame(self, text="游戏设置")
        f.pack(in_=self.scroll.inner, fill="x", pady=6)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="用户名:").pack(side="left")
        self.user_var = tk.StringVar(value=config.get("user_name", "Steve"))
        ttk.Entry(row, textvariable=self.user_var, width=16).pack(side="left", padx=4)
        ttk.Label(row, text="窗口宽:").pack(side="left")
        self.w_var = tk.StringVar(value=str(config.get("width", 854)))
        ttk.Entry(row, textvariable=self.w_var, width=6).pack(side="left", padx=2)
        ttk.Label(row, text="高:").pack(side="left")
        self.h_var = tk.StringVar(value=str(config.get("height", 480)))
        ttk.Entry(row, textvariable=self.h_var, width=6).pack(side="left", padx=2)

    def _build_server(self):
        f = ttk.LabelFrame(self, text="服务器默认值（新建服务器时生效）")
        f.pack(in_=self.scroll.inner, fill="x", pady=6)
        grid = ttk.Frame(f)
        grid.pack(fill="x", padx=6, pady=4)
        self.p_port = tk.StringVar(value=str(config.get("server_port", 25565)))
        self.p_motd = tk.StringVar(value=config.get("motd", ""))
        self.p_gm = tk.StringVar(value=config.get("gamemode", "survival"))
        self.p_diff = tk.StringVar(value=config.get("difficulty", "easy"))
        self.p_max = tk.StringVar(value=str(config.get("max_players", 8)))
        self.p_view = tk.StringVar(value=str(config.get("view_distance", 10)))
        self.p_online = tk.BooleanVar(value=config.get("online_mode", False))
        ttk.Label(grid, text="端口:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(grid, textvariable=self.p_port, width=8).grid(row=0, column=1, pady=2)
        ttk.Label(grid, text="MOTD:").grid(row=0, column=2, sticky="e", padx=4, pady=2)
        ttk.Entry(grid, textvariable=self.p_motd, width=24).grid(row=0, column=3, pady=2)
        ttk.Label(grid, text="游戏模式:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        ttk.Combobox(grid, textvariable=self.p_gm, values=("survival", "creative",
                     "adventure", "spectator"), width=8).grid(row=1, column=1, pady=2)
        ttk.Label(grid, text="难度:").grid(row=1, column=2, sticky="e", padx=4, pady=2)
        ttk.Combobox(grid, textvariable=self.p_diff, values=("peaceful", "easy",
                     "normal", "hard"), width=8).grid(row=1, column=3, pady=2)
        ttk.Label(grid, text="最大玩家:").grid(row=2, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(grid, textvariable=self.p_max, width=8).grid(row=2, column=1, pady=2)
        ttk.Label(grid, text="视距:").grid(row=2, column=2, sticky="e", padx=4, pady=2)
        ttk.Entry(grid, textvariable=self.p_view, width=8).grid(row=2, column=3, pady=2)
        ttk.Checkbutton(grid, text="正版验证", variable=self.p_online).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=2)

    def _build_misc(self):
        f = ttk.LabelFrame(self, text="其他")
        f.pack(in_=self.scroll.inner, fill="x", pady=6)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="下载镜像:").pack(side="left")
        self.mirror_var = tk.StringVar(value=config.get("mirror", "auto"))
        ttk.Combobox(row, textvariable=self.mirror_var, values=("auto", "mojang", "bmclapi"),
                     width=12).pack(side="left", padx=4)
        ttk.Button(row, text="保存全部设置", command=self.save).pack(side="left", padx=10)

    # ---- 行为 ----
    def browse_java(self):
        p = filedialog.askopenfilename(title="选择 java.exe",
                                       filetypes=[("Java", "java.exe"), ("所有文件", "*.*")])
        if p:
            self.java_var.set(p)
            self._refresh_info(p)

    def auto_java(self):
        p = java.detect_java_path()
        if p:
            self.java_var.set(p)
            self._refresh_info(p)
            messagebox.showinfo("检测", f"找到 Java: {p}")
        else:
            messagebox.showinfo("检测", "未找到已安装的 Java，请手动浏览选择。")

    def _refresh_info(self, p):
        if os.path.isfile(p):
            maj = java.java_major(p)
            self.java_info.configure(text=f"{os.path.basename(p)}  (Java {maj})")

    def save(self):
        config.set("java_path", self.java_var.get().strip())
        config.set("jvm_args", self.jvm_var.get().strip())
        config.set("server_jvm_args", self.sjvm_var.get().strip() or "-Xmx2G")
        config.set("user_name", self.user_var.get().strip() or "Steve")
        try:
            config.set("width", int(self.w_var.get() or 854))
            config.set("height", int(self.h_var.get() or 480))
        except ValueError:
            pass
        config.set("server_port", int(self.p_port.get() or 25565))
        config.set("motd", self.p_motd.get())
        config.set("gamemode", self.p_gm.get())
        config.set("difficulty", self.p_diff.get())
        config.set("max_players", int(self.p_max.get() or 8))
        config.set("view_distance", int(self.p_view.get() or 10))
        config.set("online_mode", self.p_online.get())
        config.set("mirror", self.mirror_var.get())
        messagebox.showinfo("保存", "设置已保存")
