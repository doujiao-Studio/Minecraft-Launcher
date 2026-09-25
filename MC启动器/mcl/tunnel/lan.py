"""局域网工具：枚举本机 IP、探测端口是否可连、生成局域网地址。"""
from __future__ import annotations
import socket

from .. import utils

log = utils.get_logger("lan")


def get_local_ips() -> list[str]:
    ips = set()
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            if "." in ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    # 通过 UDP 连接探测真实出口 IP（不发送数据）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ips)


def probe_port(host: str, port: int, timeout: float = 1.5) -> bool:
    """探测 host:port 是否能建立 TCP 连接（服务器是否在监听）。"""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def lan_addresses(port: int) -> list[str]:
    out = []
    for ip in get_local_ips():
        out.append(f"{ip}:{port}")
    return out
