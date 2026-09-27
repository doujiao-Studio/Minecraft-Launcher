"""服务器管理：创建实例、启停、控制台、配置、白名单/OP、备份。"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from datetime import datetime
from typing import Callable, Optional

from . import java, network, paths, utils, versions

log = utils.get_logger("server")


def server_types() -> list[str]:
    return ["vanilla", "paper"]


def list_servers() -> list[str]:
    d = paths.servers_dir()
    return sorted([n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n))])


def server_jar(name: str) -> str:
    return os.path.join(paths.server_dir(name), "server.jar")


def eula_path(name: str) -> str:
    return os.path.join(paths.server_dir(name), "eula.txt")


def props_path(name: str) -> str:
    return os.path.join(paths.server_dir(name), "server.properties")


def whitelist_path(name: str) -> str:
    return os.path.join(paths.server_dir(name), "whitelist.json")


def ops_path(name: str) -> str:
    return os.path.join(paths.server_dir(name), "ops.json")


def is_created(name: str) -> bool:
    return os.path.exists(server_jar(name))


def is_running(name: str) -> bool:
    return bool(_running.get(name))


def create_server(name: str, server_type: str, version_id: str,
                  progress: Optional[Callable[[str, float], None]] = None) -> str:
    """创建并下载服务器 jar。返回 jar 路径。"""
    sdir = paths.server_dir(name)
    if not re.match(r"^[\w\- ]+$", name):
        raise ValueError("服务器名只能包含字母数字、下划线、中划线和空格")
    if is_created(name):
        raise RuntimeError(f"服务器 {name} 已存在")
    jar = server_jar(name)
    if server_type == "vanilla":
        if progress:
            progress("下载原版服务器端", 0)
        # 优先版本 JSON 自带的 server 地址（piston-data），BMCLAPI 兜底
        srv_url = ""
        try:
            srv_url = versions.parse_version_json(version_id).get(
                "downloads", {}).get("server", {}).get("url", "")
        except Exception:
            pass
        try:
            network.download(srv_url or network.resolve_server_jar(version_id), jar)
        except network.DownloadError:
            network.download(network.resolve_server_jar(version_id), jar)
        if progress:
            progress("下载原版服务器端", 1)
    elif server_type == "paper":
        url = _paper_url(version_id)
        if progress:
            progress(f"下载 Paper {version_id}", 0)
        network.download(url, jar)
        if progress:
            progress(f"下载 Paper {version_id}", 1)
    else:
        raise ValueError(f"未知服务器类型 {server_type}")

    # 默认配置
    if not os.path.exists(eula_path(name)):
        with open(eula_path(name), "w", encoding="utf-8") as f:
            f.write("eula=true\n")
    write_props(name, _default_props())
    log.info("创建服务器 %s (%s %s)", name, server_type, version_id)
    return jar


def _paper_url(version: str) -> str:
    import urllib.parse
    api = f"https://api.papermc.io/v3/projects/paper/versions/{urllib.parse.quote(version)}/builds"
    data = network.http_json(api)
    builds = data.get("builds", [])
    if not builds:
        raise network.DownloadError(f"Paper 没有 {version} 的构建")
    b = builds[-1]
    build = b["build"]
    name = b.get("downloads", {}).get("application", {}).get("name")
    if not name:
        raise network.DownloadError("Paper 下载信息缺失")
    return f"https://api.papermc.io/v3/projects/paper/versions/{urllib.parse.quote(version)}/builds/{build}/downloads/{name}"


# ---- 配置读写 ----

def _default_props() -> dict:
    return {
        "server-port": config_port(),
        "motd": config_motd(),
        "gamemode": config_gamemode(),
        "difficulty": config_difficulty(),
        "online-mode": "false" if not config_online() else "true",
        "max-players": str(config_maxplayers()),
        "view-distance": str(config_viewdistance()),
        "spawn-protection": "16",
        "white-list": "false",
        "pvp": "true",
        "allow-nether": "true",
        "enable-command-block": "true",
        "level-type": "minecraft\\:normal",
        "generator-settings": "",
        "level-seed": "",
        "level-name": "world",
    }


def config_port() -> int:
    from . import config
    return config.get("server_port", 25565)


def config_motd() -> str:
    from . import config
    return config.get("motd", "欢迎来到我的世界!")


def config_gamemode() -> str:
    from . import config
    return config.get("gamemode", "survival")


def config_difficulty() -> str:
    from . import config
    return config.get("difficulty", "easy")


def config_online() -> bool:
    from . import config
    return config.get("online_mode", False)


def config_maxplayers() -> int:
    from . import config
    return config.get("max_players", 8)


def config_viewdistance() -> int:
    from . import config
    return config.get("view_distance", 10)


def read_props(name: str) -> dict:
    p = props_path(name)
    out = {}
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
        except Exception:
            pass
    return out


def write_props(name: str, props: dict) -> None:
    p = props_path(name)
    lines = []
    for k, v in props.items():
        lines.append(f"{k}={v}")
    with open(p, "w", encoding="utf-8") as f:
        f.write("#Minecraft server properties\n")
        f.write("#由 NCL 启动器生成\n")
        f.write("\n".join(lines) + "\n")
    log.info("写入 %s 配置", p)


def read_player_list(name: str, kind: str) -> list[str]:
    p = whitelist_path(name) if kind == "whitelist" else ops_path(name)
    out = []
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            for e in data:
                out.append(e.get("name", ""))
        except Exception:
            pass
    return [x for x in out if x]


def write_player_list(name: str, kind: str, players: list[str]) -> None:
    p = whitelist_path(name) if kind == "whitelist" else ops_path(name)
    data = [{"uuid": "", "name": u} for u in players]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- 进程管理 ----

_running: dict[str, "ServerProcess"] = {}


class ServerProcess:
    def __init__(self, name: str, on_line: Callable[[str], None],
                 on_exit: Callable[[int], None]):
        self.name = name
        self.on_line = on_line
        self.on_exit = on_exit
        self.proc: Optional[subprocess.Popen] = None
        self.started_at = time.time()

    @property
    def uptime(self) -> float:
        return time.time() - self.started_at

    def start(self) -> None:
        sdir = paths.server_dir(self.name)
        java_path = java.select_java_path(0) or java.effective_java()
        if not java_path:
            raise RuntimeError("未找到 Java，请到设置页指定 java.exe")
        jvm = java_shlex(config_jvm_args())
        cmd = [java_path, *jvm, "-jar", "server.jar", "nogui"]
        self.proc = subprocess.Popen(
            cmd, cwd=sdir, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        utils.run_thread(self._reader, f"srv-reader-{self.name}")
        utils.run_thread(self._log_writer, f"srv-logger-{self.name}")
        log.info("启动服务器 %s: %s", self.name, " ".join(cmd))

    def _reader(self) -> None:
        assert self.proc
        for line in self.proc.stdout:
            self.on_line(line.rstrip("\n"))
        code = self.proc.wait()
        if self.on_exit:
            self.on_exit(code)

    def _log_writer(self) -> None:
        # 占位：日志由外部回调写入 UI；此处保留扩展
        pass

    def send(self, text: str) -> None:
        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.write(text + "\n")
                self.proc.stdin.flush()
            except Exception:
                pass

    def stop(self, force: bool = False) -> None:
        if not self.proc:
            return
        if not force and self.proc.stdin:
            self.send("stop")
            try:
                self.proc.wait(timeout=10)
                return
            except Exception:
                pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def config_jvm_args() -> str:
    from . import config
    return config.get("server_jvm_args", "-Xmx2G")


def java_shlex(s: str) -> list[str]:
    import shlex
    try:
        return shlex.split(s)
    except Exception:
        return s.split()


def start(name: str, on_line: Callable[[str], None],
          on_exit: Optional[Callable[[int], None]] = None) -> ServerProcess:
    if is_running(name):
        raise RuntimeError(f"服务器 {name} 已在运行")
    sp = ServerProcess(name, on_line, on_exit or (lambda c: None))
    _running[name] = sp
    sp.start()
    return sp


def stop(name: str, force: bool = False) -> None:
    sp = _running.get(name)
    if not sp:
        return
    sp.stop(force)
    if sp.proc is None or sp.proc.poll() is not None:
        _running.pop(name, None)


def send_command(name: str, text: str) -> None:
    sp = _running.get(name)
    if sp:
        sp.send(text)


# ---- 备份 ----

def backup(name: str) -> str:
    """把 world 目录打成 zip。返回备份文件路径。"""
    sdir = paths.server_dir(name)
    world = os.path.join(sdir, "world")
    if not os.path.isdir(world):
        raise RuntimeError("还没有 world 目录，无法备份")
    os.makedirs(paths.base_dir(), exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(paths.base_dir(), "backups",
                        f"{name}_{stamp}.zip")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(world):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, sdir)
                z.write(full, rel)
    log.info("备份 %s -> %s", name, dest)
    return dest


def list_backups(name: str) -> list[str]:
    d = os.path.join(paths.base_dir(), "backups")
    if not os.path.isdir(d):
        return []
    return sorted([os.path.join(d, f) for f in os.listdir(d)
                   if f.startswith(name + "_") and f.endswith(".zip")],
                  reverse=True)
