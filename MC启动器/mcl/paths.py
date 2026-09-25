"""路径布局：集中管理数据目录，避免散落各处。

- base_dir / MCLauncherData：版本 jar、库、资源、配置、服务器、日志
- .minecraft：玩家游戏目录（存档 / 模组 / 资源包 / 配置），直接放在启动器文件夹内
"""
from __future__ import annotations
import os
import shutil
import sys

APP_NAME = "MCL-神启动器"


def app_root() -> str:
    """启动器文件夹根目录：源码运行 = 项目根；exe 运行 = exe 所在目录（绿色版）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_dir() -> str:
    """程序数据根目录（跟随启动器文件夹，也可用环境变量 MCL_DATA_DIR 覆盖）。"""
    env = os.environ.get("MCL_DATA_DIR")
    if env:
        return os.path.abspath(env)
    return os.path.join(app_root(), "MCLauncherData")


def minecraft_root() -> str:
    """.minecraft 根目录（直接位于启动器文件夹内）。"""
    d = os.path.join(app_root(), ".minecraft")
    os.makedirs(d, exist_ok=True)
    return d


def versions_dir() -> str:
    d = os.path.join(base_dir(), "versions")
    os.makedirs(d, exist_ok=True)
    return d


def servers_dir() -> str:
    d = os.path.join(base_dir(), "servers")
    os.makedirs(d, exist_ok=True)
    return d


def relay_dir() -> str:
    d = os.path.join(base_dir(), "relay")
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(base_dir(), "config.json")


def version_dir(version_id: str) -> str:
    d = os.path.join(versions_dir(), version_id)
    os.makedirs(d, exist_ok=True)
    return d


def libs_dir(version_id: str) -> str:
    d = os.path.join(version_dir(version_id), "libraries")
    os.makedirs(d, exist_ok=True)
    return d


def natives_dir(version_id: str) -> str:
    d = os.path.join(version_dir(version_id), "natives")
    os.makedirs(d, exist_ok=True)
    return d


def assets_dir(version_id: str) -> str:
    d = os.path.join(version_dir(version_id), "assets")
    os.makedirs(d, exist_ok=True)
    return d


def game_dir(version_id: str) -> str:
    """玩家游戏目录（.minecraft/<版本>）：存档 / 模组 / 资源包 / 配置所在。"""
    _migrate_game(version_id)
    d = os.path.join(minecraft_root(), version_id)
    os.makedirs(d, exist_ok=True)
    return d


def _migrate_game(version_id: str) -> None:
    """一次性迁移：把旧版 `MCLauncherData/versions/<id>/game` 的游戏数据挪到 `.minecraft/<id>`。"""
    old = os.path.join(versions_dir(), version_id, "game")
    new = os.path.join(minecraft_root(), version_id)
    if not os.path.isdir(old):
        return
    if os.path.exists(new):
        return  # 新位置已有数据，不覆盖
    try:
        shutil.move(old, new)
    except Exception as e:
        log_err = f"[MCL] 游戏目录迁移失败 {old} -> {new}: {e}"
        try:
            import mcl.utils as u
            u.get_logger("paths").warning("%s", log_err)
        except Exception:
            pass


def server_dir(name: str) -> str:
    d = os.path.join(servers_dir(), name)
    os.makedirs(d, exist_ok=True)
    return d


def log_dir() -> str:
    d = os.path.join(base_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def resource_path(*parts: str) -> str:
    """兼容打包为 exe 时获取资源文件的路径。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)
