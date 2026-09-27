"""全局配置：JSON 读写，线程安全，默认值合并。"""
from __future__ import annotations
import json
import os
import threading
import uuid
from . import paths

_lock = threading.RLock()

DEFAULTS = {
    # 启动器
    "java_path": "",            # 留空则自动检测
    "jvm_args": "-Xmx4G -Xms1G",
    "user_name": "Steve",
    "auth_mode": "offline",     # offline / yggdrasil / microsoft（兼容旧配置）
    "access_token": "",
    "uuid": "",
    # 账户（详见 mcl/accounts.py）：留空则用内置默认客户端 ID
    "ms_client_id": "",
    "ygg_url": "",              # 外置登录/皮肤站地址，如 https://skin.example.com/api/yggdrasil
    "ygg_client_token": "",
    "width": 854,
    "height": 480,
    "mirror": "auto",           # auto / mojang / bmclapi
    "max_players": 8,
    "view_distance": 10,
    "motd": "欢迎来到我的世界!",
    "gamemode": "survival",
    "difficulty": "easy",
    "online_mode": False,
    "server_port": 25565,
    "relay_host": "",           # 自建中继服务器地址
    "relay_control_port": 6000,
    "relay_token": "",
    "relay_remote_port": 25565,
    "last_tab": "launcher",
}

_cfg: dict | None = None


def _file() -> str:
    return paths.config_path()


def load() -> dict:
    global _cfg
    with _lock:
        if _cfg is not None:
            return _cfg
        data = {}
        p = _file()
        existed = os.path.exists(p)
        if existed:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in data.items() if k in DEFAULTS})
        if not merged.get("uuid"):
            merged["uuid"] = str(uuid.uuid4())
        _cfg = merged
        if not existed:
            save()  # 首次运行：立即落盘一份默认配置
        return _cfg


def save() -> None:
    with _lock:
        p = _file()
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(_cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def get(key: str, default=None):
    return load().get(key, default)


def set(key: str, value) -> None:
    with _lock:
        load()[key] = value
        save()
