"""Java 检测：自动发现系统已安装的 Java，判断主版本号。"""
from __future__ import annotations
import os
import platform
import re
import string
import subprocess
from typing import Optional

from . import config, utils

log = utils.get_logger("java")


def _candidate_paths() -> list[str]:
    cands: list[str] = []
    # 常见安装目录
    for root in (os.environ.get("ProgramFiles", "C:/Program Files"),
                 os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"),
                 os.path.expandvars(r"%LOCALAPPDATA%"),
                 os.path.expanduser("~")):
        for base in ("Java", "jdk", "jre", "Eclipse Adoptium", "Microsoft",
                     "Zulu", "Temurin", "Liberica", "Amazon Corretto",
                     "Oracle", "jdk", "GraalVM"):
            d = os.path.join(root, base)
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                p = os.path.join(d, name, "bin", "java.exe")
                if os.path.isfile(p):
                    cands.append(p)
    # 所有磁盘根目录下的 java/jdk/jre 目录（覆盖 D:\java 17、D:\java21 等）
    _prefixes = ("java", "jdk", "jre", "temurin", "corretto",
                 "zulu", "graal", "liberica", "openjdk")
    for drive in _all_drives():
        try:
            entries = os.listdir(drive)
        except OSError:
            continue
        for name in entries:
            low = name.lower()
            if low.startswith(_prefixes):
                p = os.path.join(drive, name, "bin", "java.exe")
                if os.path.isfile(p):
                    cands.append(p)
                # 也试 盘根\<java目录>\<子目录> 两级
                inner = os.path.join(drive, name)
                try:
                    for sub in os.listdir(inner):
                        p2 = os.path.join(inner, sub, "bin", "java.exe")
                        if os.path.isfile(p2):
                            cands.append(p2)
                except OSError:
                    pass
    # PATH 中直接暴露的 java.exe
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d:
            continue
        p = os.path.join(d, "java.exe")
        if os.path.isfile(p):
            cands.append(p)
    # JAVA_HOME
    jh = os.environ.get("JAVA_HOME")
    if jh:
        p = os.path.join(jh, "bin", "java.exe")
        if os.path.isfile(p):
            cands.append(p)
    return cands


def _all_drives() -> list[str]:
    drives = []
    for letter in string.ascii_uppercase:
        d = f"{letter}:\\"
        if os.path.isdir(d):
            drives.append(d)
    return drives


def detect_java_path() -> Optional[str]:
    """返回本机最高版本的一个可用 java.exe（自动检测应选最好的）。"""
    avail = available_java()
    return avail[0][1] if avail else None


def is_java(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    try:
        r = subprocess.run([path, "-version"], capture_output=True,
                           text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def java_major(path: str) -> int:
    """解析 java 主版本号（17 表示 Java 17）。解析失败返回 0。"""
    if not path:
        return 0
    try:
        r = subprocess.run([path, "-version"], capture_output=True,
                           text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        out = r.stdout + "\n" + r.stderr
        m = re.search(r'"(\d+)(?:\.(\d+))?', out)
        if m:
            first = int(m.group(1))
            if first == 1 and m.group(2):
                # 老式版本号 1.8 -> 8
                return int(m.group(2))
            return first
    except Exception:
        pass
    return 0


def effective_java() -> str:
    """配置优先，其次自动选择本机最高的 Java。"""
    p = config.get("java_path", "")
    if p and os.path.isfile(p):
        return p
    found = detect_java_path()
    if found:
        config.set("java_path", found)
        return found
    return ""


def available_java() -> list[tuple[int, str]]:
    """返回本机所有可用 Java，按主版本降序: [(major, path), ...]。"""
    out = []
    seen = set()
    for p in _candidate_paths():
        if p in seen:
            continue
        seen.add(p)
        maj = java_major(p)
        if maj > 0:
            out.append((maj, p))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def highest_java() -> str:
    """返回本机最高版本的 java.exe（无则空串）。"""
    avail = available_java()
    return avail[0][1] if avail else ""


def select_java_path(min_major: int = 0) -> str:
    """挑选满足主版本 >= min_major 的 Java（优先最高）。不满足返回空串。"""
    avail = available_java()
    if not avail:
        return ""
    if min_major > 0:
        for maj, path in avail:
            if maj >= min_major:
                return path
        return ""
    return avail[0][1]
