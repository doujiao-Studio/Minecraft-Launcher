"""Modrinth 下载中心：搜索并安装 模组 / 资源包 / 数据包。"""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from typing import Optional

from . import network, paths, utils

log = utils.get_logger("modrinth")
API = "https://api.modrinth.com/v2"

# 项目类型 -> 中文
PROJECT_TYPES = {
    "mod": "模组",
    "resourcepack": "资源包",
    "datapack": "数据包",
    "modpack": "整合包",
    "shader": "光影",
    "plugin": "插件",
}

# 常用加载器
LOADERS = ["forge", "fabric", "neoforge", "quilt"]

COMMON_VERSIONS = [
    "1.21.6", "1.21.5", "1.21.4", "1.21.3", "1.21.1", "1.21",
    "1.20.6", "1.20.4", "1.20.1", "1.20", "1.19.4", "1.19.2",
    "1.18.2", "1.17.1", "1.16.5", "1.15.2", "1.14.4", "1.12.2",
]


class ModrinthError(Exception):
    pass


def _get(url: str, params: Optional[dict] = None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "MCL-ShenLauncher/1.0 (mod download center)"})
    import time
    last: Optional[Exception] = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ModrinthError(f"Modrinth HTTP {e.code}") from e
        except Exception as e:
            last = e
            if attempt < 2:
                time.sleep(1.2 * (attempt + 1))
                continue
    raise ModrinthError(f"Modrinth 网络错误: {last}") from last


def search_projects(query: str, ptype: str = "mod", version: str = "",
                    loader: str = "", limit: int = 30) -> list[dict]:
    facets: list[list[str]] = []
    if ptype:
        facets.append(["project_type:" + ptype])
    if version:
        facets.append(["versions:" + version])
    if loader:
        facets.append(["categories:" + loader])
    params: dict = {"query": query, "limit": limit, "index": "downloads"}
    if facets:
        params["facets"] = json.dumps(facets)
    data = _get(f"{API}/search", params)
    out = []
    for h in data.get("hits", []):
        out.append({
            "project_id": h.get("project_id", ""),
            "slug": h.get("slug", ""),
            "title": h.get("title", ""),
            "description": (h.get("description") or "").strip(),
            "author": h.get("author", ""),
            "downloads": h.get("downloads", 0),
            "icon": h.get("icon_url", ""),
        })
    return out


def get_versions(project_id: str, version: str = "", loader: str = "") -> list[dict]:
    params: dict = {}
    if version:
        params["game_versions"] = json.dumps([version])
    if loader:
        params["loaders"] = json.dumps([loader])
    data = _get(f"{API}/project/{project_id}/version", params)
    out = []
    for v in data:
        out.append({
            "id": v.get("id", ""),
            "name": v.get("name", ""),
            "version_number": v.get("version_number", ""),
            "game_versions": v.get("game_versions", []),
            "loaders": v.get("loaders", []),
            "date": v.get("date_published", ""),
            "files": v.get("files", []),
        })
    return out


def best_file(version: dict) -> Optional[dict]:
    files = version.get("files", [])
    for f in files:
        if f.get("primary"):
            return f
    return files[0] if files else None


def install_file(file_info: dict, dest_dir: str) -> str:
    """下载模组/资源包/数据包文件到目标目录。"""
    url = file_info.get("url", "")
    fname = file_info.get("filename", "download.jar")
    if not url:
        raise ModrinthError("该文件没有下载地址")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, fname)
    if os.path.exists(dest):
        return dest
    network.download(url, dest)
    log.info("已安装 %s -> %s", fname, dest)
    return dest


# ---- 目标目录计算 ----

def install_target_dir(install_to: str, server_name: str, ptype: str,
                       version_id: str, world_name: str = "") -> tuple[str, str]:
    """根据安装位置/类型算出目录。返回 (目录, 说明)。"""
    if install_to == "server":
        base = paths.server_dir(server_name)
        if ptype == "datapack":
            return os.path.join(base, "world", "datapacks"), "服务器存档数据包"
        if ptype == "resourcepack":
            return os.path.join(base, "resourcepacks"), "服务器资源包目录"
        return os.path.join(base, "mods"), "服务器模组目录"

    # 客户端
    gdir = paths.game_dir(version_id)
    if ptype == "datapack":
        if world_name:
            return os.path.join(gdir, "saves", world_name, "datapacks"), f"存档 {world_name} 数据包"
        return os.path.join(gdir, "datapacks"), "客户端数据包（需配合存档使用）"
    if ptype == "resourcepack":
        return os.path.join(gdir, "resourcepacks"), "客户端资源包目录"
    return os.path.join(gdir, "mods"), "客户端模组目录"


def client_worlds(version_id: str) -> list[str]:
    """列出某游戏版本下的存档。"""
    saves = os.path.join(paths.game_dir(version_id), "saves")
    if not os.path.isdir(saves):
        return []
    return sorted([n for n in os.listdir(saves)
                   if os.path.isdir(os.path.join(saves, n))])
