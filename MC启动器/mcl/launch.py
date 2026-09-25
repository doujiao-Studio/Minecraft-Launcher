"""启动器核心：下载客户端资源、解析版本 JSON、装配并运行启动命令。"""
from __future__ import annotations
import json
import os
import re
import subprocess
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from . import config, java, network, paths, utils, versions

log = utils.get_logger("launch")

Progress = Callable[[str, float, float], None]  # (阶段, 已完成, 总计)
_NOPROG: Progress = lambda stage, done, total: None
_MAX_WORKERS = 16  # 并发下载线程数


def _verify(path: str, sha1: Optional[str]) -> bool:
    if not os.path.exists(path):
        return False
    if sha1:
        try:
            return utils.sha1_file(path) == sha1
        except Exception:
            return False
    return os.path.getsize(path) > 0


def download_client(version_id: str, progress: Progress = _NOPROG) -> None:
    """下载 client jar + 所有库 + 资源索引 + 原生库。"""
    vjson = versions.parse_version_json(version_id)
    libs = versions.collect_libraries(vjson)

    # 1. 客户端主 jar（优先版本 JSON 自带地址 piston-data，实测国内可达；BMCLAPI 兜底）
    client_path = os.path.join(paths.version_dir(version_id), "client.jar")
    if not _verify(client_path, None):
        progress("客户端", 0, 1)
        cj = vjson.get("downloads", {}).get("client", {}).get("url", "")
        try:
            network.download(cj or network.resolve_client_jar(version_id), client_path)
        except network.DownloadError:
            network.download(network.resolve_client_jar(version_id), client_path)
        progress("客户端", 1, 1)

    # 2. 库文件（含原生库）——并发下载
    total = len(libs)
    _dl_many([(lib.path, lib.sha1, lib.url) for lib in libs],
             lambda d, t: progress(f"库文件 {int(d)}/{int(t)}", d, t),
             base=paths.libs_dir(version_id))

    # 3. 原生库解压
    extract_natives(version_id, libs)

    # 4. 资源索引 + 对象（并发下载）
    download_assets(version_id, progress, vjson)

    progress("完成", 1, 1)


def _dl_one(dest: str, sha1: Optional[str], url: str, base: str) -> bool:
    full = os.path.join(base, dest)
    if _verify(full, sha1):
        return True
    try:
        network.download(url or network.resolve_library(dest), full,
                         expected_sha1=sha1)
        return True
    except network.DownloadError:
        # 主地址失败时回退镜像
        try:
            network.download(network.resolve_library(dest), full,
                             expected_sha1=sha1)
            return True
        except network.DownloadError as e:
            log.warning("库下载失败跳过 %s: %s", dest, e)
            return False


def _dl_many(items: list[tuple], prog: Progress, base: str) -> None:
    """并发下载一批文件，prog(完成数, 总数)。items: (相对路径, sha1, url)。"""
    total = len(items)
    if not total:
        prog(0, 0)
        return
    done = 0
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futs = [ex.submit(_dl_one, p, s, u, base) for (p, s, u) in items]
        for _ in as_completed(futs):
            done += 1
            prog(done, total)


def extract_natives(version_id: str, libs: list[versions.Library]) -> None:
    ndir = paths.natives_dir(version_id)
    for lib in libs:
        if not lib.natives:
            continue
        jar = os.path.join(paths.libs_dir(version_id), lib.path)
        if not os.path.exists(jar):
            continue
        try:
            with zipfile.ZipFile(jar) as z:
                for member in z.namelist():
                    base = os.path.basename(member)
                    if not base:
                        continue
                    if not (base.endswith(".dll") or base.endswith(".so")
                            or base.endswith(".dylib")):
                        continue
                    out = os.path.join(ndir, base)
                    with z.open(member) as src, open(out, "wb") as dst:
                        dst.write(src.read())
        except Exception as e:
            log.warning("解压原生库失败 %s: %s", jar, e)


def download_assets(version_id: str, progress: Progress = _NOPROG,
                    vjson: Optional[dict] = None) -> None:
    vjson = vjson or versions.parse_version_json(version_id)
    ai = versions.asset_index_info(vjson)
    if not ai:
        return
    index_file = os.path.join(paths.assets_dir(version_id), f"{ai['id']}.json")
    if not _verify(index_file, ai.get("sha1")):
        # 优先用版本 JSON 自带的索引地址（piston-meta，国内可访问），失败再回退镜像
        candidates = [u for u in (ai.get("url", ""), network.resolve_asset_index(ai["id"]))
                      if u]
        downloaded = False
        for u in candidates:
            try:
                network.download(u, index_file, expected_sha1=ai.get("sha1"))
                downloaded = True
                break
            except network.DownloadError as e:
                log.warning("索引下载失败，尝试下一个: %s (%s)", u, e)
        if not downloaded:
            log.warning("资源索引 %s 全部下载失败", ai["id"])
            return
    try:
        with open(index_file, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        return
    objs = index.get("objects", {})
    items = list(objs.items())
    total = len(items)
    # 先筛出需要下载的（并发）
    need = []
    for name, meta in items:
        h = meta.get("hash", "")
        if not h:
            continue
        dest = os.path.join(paths.assets_dir(version_id), "objects", h[0:2], h)
        if not _verify(dest, h):
            need.append((name, h, dest))
    if need:
        done = total - len(need)
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            futs = [ex.submit(_dl_asset, h, dest) for (_n, h, dest) in need]
            for _ in as_completed(futs):
                done += 1
                progress(f"资源 {int(done)}/{int(total)}", done, total)
    else:
        progress(f"资源 {total}/{total}", total, total)


def _dl_asset(hash_hex: str, dest: str) -> None:
    # 优先 Mojang 资源节点（国内实测快），BMCLAPI 兜底
    urls = []
    if config.get("mirror", "auto") != "bmclapi":
        urls.append(f"{network.MOJANG_RES}/{hash_hex[0:2]}/{hash_hex}")
    urls.append(network.resolve_asset(hash_hex))
    for u in dict.fromkeys(urls):
        try:
            network.download(u, dest, expected_sha1=hash_hex)
            return
        except network.DownloadError as e:
            log.debug("资源 %s 下载失败: %s", hash_hex[:8], e)


def build_launch_command(version_id: str, workdir: Optional[str] = None) -> list[str]:
    vjson = versions.parse_version_json(version_id)
    required = versions.required_java(vjson)
    java_path = java.select_java_path(required)
    if not java_path:
        best = java.highest_java()
        best_major = java.java_major(best)
        raise RuntimeError(
            f"版本 {version_id} 需要 Java {required}，但本机最高只有 Java {best_major}"
            f"（{best or '未找到'}）。\n请安装 Java {required} 或更高的版本，"
            f"或换用更低的 MC 版本。")

    libs = versions.collect_libraries(vjson)
    cp_entries = [os.path.join(paths.libs_dir(version_id), l.path) for l in libs]
    cp_entries.append(os.path.join(paths.version_dir(version_id), "client.jar"))
    classpath = os.pathsep.join([c for c in cp_entries if os.path.exists(c)])

    natives = paths.natives_dir(version_id)
    assets = paths.assets_dir(version_id)
    gdir = paths.game_dir(version_id)
    if workdir:
        gdir = os.path.abspath(workdir)

    ai = versions.asset_index_info(vjson)
    index_id = ai["id"] if ai else "legacy"

    cmd = [
        java_path,
        *shlex_args(config.get("jvm_args", "")),
        "-Djava.library.path=" + natives,
        "-cp", classpath,
        versions.main_class(vjson),
        "--username", config.get("user_name", "Steve"),
        "--version", version_id,
        "--gameDir", gdir,
        "--assetsDir", assets,
        "--assetIndex", index_id,
        "--uuid", config.get("uuid", ""),
        "--accessToken", config.get("access_token", "0"),
        "--userType", "mojang" if config.get("auth_mode") == "yggdrasil" else "legacy",
        "--versionType", vjson.get("type", "release"),
        "--userProperties", "{}",
        "--width", str(config.get("width", 854)),
        "--height", str(config.get("height", 480)),
    ]
    return cmd


def shlex_args(s: str) -> list[str]:
    """极简参数拆分，支持引号。"""
    import shlex
    try:
        return shlex.split(s)
    except Exception:
        return s.split()


class GameProcess:
    """管理一个游戏进程，把输出流转发到回调。"""

    def __init__(self, cmd: list[str], on_line: Callable[[str], None],
                 workdir: str = None, on_exit: Callable[[int], None] = None):
        self.cmd = cmd
        self.on_line = on_line
        self.on_exit = on_exit
        self.workdir = workdir or paths.base_dir()
        self.proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.cmd, cwd=self.workdir, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        utils.run_thread(self._reader, "game-reader")

    def _reader(self) -> None:
        assert self.proc
        for line in self.proc.stdout:
            self.on_line(line.rstrip("\n"))
        code = self.proc.wait()
        if self.on_exit:
            self.on_exit(code)

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
                self.proc.wait(timeout=8)
                return
            except Exception:
                pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
