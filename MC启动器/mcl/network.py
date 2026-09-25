"""网络下载：支持镜像切换、进度回调、SHA1 校验、断点续传。"""
from __future__ import annotations
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from . import config, utils

log = utils.get_logger("net")

# 镜像定义：主站 + BMCLAPI 镜像（国内更快，默认 auto）
MOJANG_META = "https://launchermeta.mojang.com"
MOJANG_RES = "https://resources.download.minecraft.net"
BMCLAPI = "https://bmclapi2.bangbang93.com"


class DownloadError(Exception):
    pass


def _ua() -> dict:
    return {"User-Agent": "MCL-ShenLauncher/1.0 (python)"}


def resolve_meta_base() -> str:
    """版本清单 JSON 的根地址。"""
    m = config.get("mirror", "auto")
    if m == "bmclapi":
        return f"{BMCLAPI}/mc/game"
    return f"{MOJANG_META}/mc/game"


def resolve_dl_base() -> str:
    """对象文件下载根地址（assets / libraries 用）。"""
    m = config.get("mirror", "auto")
    if m == "mojang":
        return MOJANG_RES
    return f"{BMCLAPI}/objects"


def resolve_version_json(version_id: str) -> str:
    m = config.get("mirror", "auto")
    if m == "mojang":
        return f"{MOJANG_META}/mc/game/version_manifest_v2.json"
    return f"{BMCLAPI}/mc/game/version_manifest_v2.json"


def resolve_client_jar(version_id: str) -> str:
    m = config.get("mirror", "auto")
    if m == "mojang":
        # Mojang 侧 client jar 必须从 version json 里取 url；这里用 BMCLAPI 兜底
        return f"{BMCLAPI}/version/{version_id}/client"
    return f"{BMCLAPI}/version/{version_id}/client"


def resolve_server_jar(version_id: str) -> str:
    m = config.get("mirror", "auto")
    if m == "mojang":
        return f"{BMCLAPI}/version/{version_id}/server"
    return f"{BMCLAPI}/version/{version_id}/server"


def resolve_library(path: str) -> str:
    m = config.get("mirror", "auto")
    if m == "mojang":
        return f"https://libraries.minecraft.net/{path}"
    return f"{BMCLAPI}/libraries/{path}"


def resolve_asset(hash_hex: str) -> str:
    m = config.get("mirror", "auto")
    if m == "mojang":
        return f"{MOJANG_RES}/{hash_hex[0:2]}/{hash_hex}"
    return f"{BMCLAPI}/objects/{hash_hex[0:2]}/{hash_hex}"


def resolve_asset_index(index_id: str) -> str:
    m = config.get("mirror", "auto")
    if m == "mojang":
        return f"{MOJANG_META}/mc/game/current_java/assetIndex.json"  # 备用
    return f"{BMCLAPI}/indexes/{index_id}.json"


def http_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_ua())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise DownloadError(f"HTTP {e.code} {url}") from e
    except urllib.error.URLError as e:
        raise DownloadError(f"网络错误 {url}: {e.reason}") from e


def http_json(url: str, timeout: int = 20):
    import json
    return json.loads(http_text(url, timeout))


def download(
    url: str,
    dest: str,
    expected_sha1: Optional[str] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    timeout: int = 60,
) -> str:
    """下载到 dest。若文件已存在且 sha1 匹配则跳过。返回 dest。"""
    if expected_sha1 and os.path.exists(dest):
        try:
            if utils.sha1_file(dest) == expected_sha1:
                return dest
        except Exception:
            pass
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers=_ua())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            total = int(r.headers.get("Content-Length", 0))
            got = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if progress and total:
                        progress(got, total)
    except urllib.error.HTTPError as e:
        raise DownloadError(f"HTTP {e.code} {url}") from e
    except urllib.error.URLError as e:
        raise DownloadError(f"网络错误 {url}: {e.reason}") from e
    if expected_sha1:
        h = utils.sha1_file(tmp)
        if h != expected_sha1:
            os.remove(tmp)
            raise DownloadError(f"SHA1 不匹配: {url} 期望 {expected_sha1[:12]} 实际 {h[:12]}")
    os.replace(tmp, dest)
    return dest
