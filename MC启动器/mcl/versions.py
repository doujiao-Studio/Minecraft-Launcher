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


def fetch_version_manifest() -> list[VersionInfo]:
    """获取版本清单（release + snapshot）。"""
    data = network.http_json(network.resolve_version_json(""))
    out = []
    for v in data.get("versions", []):
        out.append(VersionInfo(id=v["id"], type=v.get("type", "release"),
                               url=v.get("url", ""), time=v.get("time", "")))
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
