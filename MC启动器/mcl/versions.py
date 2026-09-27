"""版本管理：版本清单、单个版本 JSON 解析、库路径 / 原生库处理。"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Optional

from . import network, paths, utils

log = utils.get_logger("versions")


@dataclass
class VersionInfo:
    id: str
    type: str = "release"
    url: str = ""
    time: str = ""


def fetch_version_manifest(retries: int = 3) -> list[VersionInfo]:
    """获取版本清单（release + snapshot）。

    失败自动重试（清单较大，弱网下容易超时），并按 id 去重——
    镜像偶发返回重复 id，若不去重，UI 侧 insert 会因 iid 冲突中断，
    导致列表「加载到一半就停了」。
    """
    data = None
    last: Optional[Exception] = None
    for _ in range(max(1, retries)):
        try:
            data = network.http_json(network.resolve_version_json(""), timeout=30)
            break
        except network.DownloadError as e:
            last = e
        except Exception as e:
            # 兜底：超时/JSON 解析失败等一律转成 DownloadError，
            # 否则上层 catch DownloadError 会漏掉，UI 卡在「正在拉取…」。
            last = network.DownloadError(str(e))
    if data is None:
        raise network.DownloadError(f"获取版本清单失败: {last}")

    out: list[VersionInfo] = []
    seen: set[str] = set()
    for v in data.get("versions", []):
        vid = v.get("id")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        # 注意：清单里 `time` 是镜像刷新版本 JSON 的时间（会批量变动），
        # 排序/展示必须用 `releaseTime`（真实发布日期），否则旧版本会被
        # 顶到列表最前面，看起来像「主要版本丢失」。
        out.append(VersionInfo(id=vid, type=v.get("type", "release"),
                               url=v.get("url", ""),
                               time=v.get("releaseTime") or v.get("time", "")))
    out.sort(key=lambda x: x.time, reverse=True)
    return out


@dataclass
class Library:
    path: str          # 如 net/minecraft/launchwrapper/1.12/launchwrapper-1.12.jar
    url: str = ""
    sha1: str = ""
    size: int = 0
    natives: str = ""  # 若是原生库，给出分类器名


def parse_version_json(version_id: str) -> dict:
    """返回解析后的版本 JSON（带缓存）。"""
    vdir = paths.version_dir(version_id)
    cached = os.path.join(vdir, "version.json")
    data = None
    if os.path.exists(cached):
        try:
            with open(cached, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None
    if not data:
        url = f"{network.BMCLAPI}/version/{version_id}/json"
        try:
            data = network.http_json(url)
        except network.DownloadError:
            # 回退 Mojang
            url = f"{network.MOJANG_META}/mc/game/version_manifest_v2.json"
            man = network.http_json(url)
            for v in man["versions"]:
                if v["id"] == version_id:
                    data = network.http_json(v["url"])
                    break
        if not data:
            raise network.DownloadError(f"无法获取版本 {version_id} 的 json")
        with open(cached, "w", encoding="utf-8") as f:
            json.dump(data, f)
    return data


def collect_libraries(version_json: dict, os_name: str = "windows") -> list[Library]:
    """展开版本 JSON 的 libraries，得到需要下载的 jar 列表。"""
    libs: list[Library] = []
    java_major = version_json.get("javaVersion", {}).get("majorVersion", 8)
    for entry in version_json.get("libraries", []):
        # 规则过滤
        rules = entry.get("rules")
        if rules and not _rules_allow(rules, os_name):
            continue
        name = entry.get("name", "")
        if "natives-" in name and not entry.get("downloads"):
            continue
        downloads = entry.get("downloads", {})
        artifact = downloads.get("artifact")
        if artifact:
            libs.append(Library(path=artifact.get("path", name),
                                url=artifact.get("url", ""),
                                sha1=artifact.get("sha1", ""),
                                size=artifact.get("size", 0)))
        classifiers = downloads.get("classifiers", {})
        native_key = f"natives-{os_name}"
        native = classifiers.get(native_key)
        if native:
            libs.append(Library(path=native.get("path", name),
                                url=native.get("url", ""),
                                sha1=native.get("sha1", ""),
                                size=native.get("size", 0),
                                natives=native_key))
    return libs


def _rules_allow(rules: list, os_name: str) -> bool:
    allow = False
    for r in rules:
        action = r.get("action", "allow")
        os_rule = r.get("os")
        match = True
        if os_rule:
            match = os_rule.get("name", "") == os_name
        if match:
            allow = action == "allow"
    return allow


def asset_index_info(version_json: dict) -> Optional[dict]:
    ai = version_json.get("assetIndex")
    if not ai:
        return None
    return {"id": ai["id"], "url": ai.get("url", ""), "sha1": ai.get("sha1", "")}


def required_java(version_json: dict) -> int:
    return version_json.get("javaVersion", {}).get("majorVersion", 8)


def launch_args(version_json: dict) -> list:
    return version_json.get("arguments", {}).get("game", [])


def main_class(version_json: dict) -> str:
    return version_json.get("mainClass", "net.minecraft.client.main.Main")
