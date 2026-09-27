"""路径布局：集中管理数据目录，避免散落各处。

- base_dir / NCLData：版本 jar、库、资源、配置、服务器、日志
- .minecraft：玩家游戏目录（存档 / 模组 / 资源包 / 配置），直接放在启动器文件夹内
"""
from __future__ import annotations
import os
import shutil
import sys

APP_NAME = "NCL 启动器"

# 首次运行时自动铺开的目录骨架
DATA_SUBDIRS = ("versions", "servers", "relay", "logs", "cache", "cache/icons")
MC_SUBDIRS = ("saves", "mods", "resourcepacks", "shaderpacks",
              "screenshots", "config", "logs", "crash-reports")

_FALLBACK: str | None = None


def app_root() -> str:
    """启动器文件夹根目录：源码运行 = 项目根；exe 运行 = exe 所在目录（绿色版）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_writable(d: str) -> bool:
    """探测目录是否可写（exe 放在 Program Files / 受保护目录时会失败）。"""
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".ncl_write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return True
    except Exception:
        return False


def data_root() -> str:
    """数据落盘根目录：优先 exe 所在目录（绿色版），不可写则回退 %LOCALAPPDATA%。"""
    global _FALLBACK
    env = os.environ.get("NCL_DATA_DIR")
    if env:
        return os.path.abspath(env)
    if _FALLBACK:
        return _FALLBACK
    root = app_root()
    if _is_writable(root):
        _FALLBACK = root
    else:
        _FALLBACK = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
            "NCL-Launcher")
    return _FALLBACK


def base_dir() -> str:
    """程序数据根目录（跟随启动器文件夹，也可用环境变量 NCL_DATA_DIR 覆盖）。"""
    env = os.environ.get("NCL_DATA_DIR")
    d = os.path.abspath(env) if env else os.path.join(data_root(), "NCLData")
    os.makedirs(d, exist_ok=True)
    return d


def minecraft_root() -> str:
    """.minecraft 根目录（直接位于启动器文件夹内）。"""
    d = os.path.join(data_root(), ".minecraft")
    os.makedirs(d, exist_ok=True)
    return d


# ---------- 首次运行自举（单 exe 双击即用） ----------
def _marker_path() -> str:
    return os.path.join(base_dir(), ".initialized")


def is_first_run() -> bool:
    """是否首次运行（尚无初始化标记）。"""
    return not os.path.exists(_marker_path())


def mark_initialized() -> None:
    try:
        with open(_marker_path(), "w", encoding="utf-8") as f:
            f.write("ok")
    except Exception:
        pass


def ensure_layout() -> dict:
    """一次性铺开所有数据目录：NCLData/* 与 .minecraft/*。

    单文件 exe 双击即可用——不需要预先打包任何数据文件夹。
    返回 {root, minecraft, created, first_run}。
    """
    created: list[str] = []
    targets = [base_dir()]
    targets += [os.path.join(base_dir(), s) for s in DATA_SUBDIRS]
    targets += [minecraft_root()]
    targets += [os.path.join(minecraft_root(), s) for s in MC_SUBDIRS]
    for d in targets:
        if not os.path.isdir(d):
            try:
                os.makedirs(d, exist_ok=True)
                created.append(d)
            except Exception:
                pass
    return {"root": base_dir(), "minecraft": minecraft_root(),
            "created": created, "first_run": is_first_run()}


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
    """一次性迁移：把旧版 `NCLData/versions/<id>/game` 的游戏数据挪到 `.minecraft/<id>`。"""
    old = os.path.join(versions_dir(), version_id, "game")
    new = os.path.join(minecraft_root(), version_id)
    if not os.path.isdir(old):
        return
    if os.path.exists(new):
        return  # 新位置已有数据，不覆盖
    try:
        shutil.move(old, new)
    except Exception as e:
        log_err = f"[NCL] 游戏目录迁移失败 {old} -> {new}: {e}"
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
