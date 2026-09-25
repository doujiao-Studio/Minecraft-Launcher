"""内网穿透：局域网直连 + 自建中继隧道（无公网 IP 也能让好友连进来）。"""
from .lan import get_local_ips, probe_port, lan_addresses
from .relay import TunnelClient, TunnelError
from . import relay_server
