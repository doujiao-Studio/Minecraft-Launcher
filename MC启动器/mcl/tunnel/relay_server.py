"""中继服务器端：运行在任何有公网 IP 的机器（免费云主机 / 同学的公网主机）上。

每个隧道分配两个端口：
  - 公网端口：玩家用它连接（等同你的服务器地址）
  - 回连端口：仅你的客户端使用，建立数据转发会话

流程：
  玩家 -> 公网端口 ->(排队)-> 通知客户端 -> 客户端连回连端口 -> 中继把两条连接对接
"""
from __future__ import annotations
import argparse
import json
import queue
import socket
import threading
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcl import utils

log = utils.get_logger("relay-server")
RECV = 65536


def _auto_public_host() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class RelayServer:
    def __init__(self, token: str, control_port: int, data_low: int, data_high: int,
                 public_host: str):
        self.token = token
        self.control_port = control_port
        self.data_low = data_low
        self.data_high = data_high
        self.public_host = public_host or _auto_public_host()
        self._running = True
        self._port_lock = threading.Lock()
        self._used_ports: set[int] = set()
        self._sessions: dict[str, dict] = {}

    # ---- 端口分配 ----
    def _alloc_port(self) -> Optional[int]:
        with self._port_lock:
            for p in range(self.data_low, self.data_high + 1):
                if p not in self._used_ports:
                    self._used_ports.add(p)
                    return p
        return None

    def _free_ports(self, *ports) -> None:
        with self._port_lock:
            for p in ports:
                self._used_ports.discard(p)

    def run(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", self.control_port))
        listener.listen(64)
        log.info("中继启动：控制端口 %s，数据端口 %s-%s，公网地址 %s",
                 self.control_port, self.data_low, self.data_high, self.public_host)
        print(f"[NCL中继] 控制端口 {self.control_port} | 数据端口范围 {self.data_low}-{self.data_high}")
        print(f"[NCL中继] 公网地址 {self.public_host} | token: {self.token}")
        try:
            while self._running:
                conn, addr = listener.accept()
                utils.run_thread(self._handle_control, "relay-ctl", args=(conn, addr))
        finally:
            listener.close()

    # ---- 控制通道 ----
    def _handle_control(self, conn: socket.socket, addr) -> None:
        conn.settimeout(60)
        buf = ""
        sid = None
        try:
            while True:
                data = conn.recv(RECV)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    if msg.get("cmd") == "register":
                        sid = self._do_register(conn, addr, msg)
        except (socket.timeout, OSError):
            pass
        finally:
            if sid:
                self._cleanup(sid)
            try:
                conn.close()
            except Exception:
                pass

    def _do_register(self, conn, addr, msg) -> Optional[str]:
        if msg.get("token") != self.token:
            self._send(conn, {"cmd": "error", "message": "token 错误"})
            return None
        pub = self._alloc_port()
        rev = self._alloc_port()
        if pub is None or rev is None:
            if pub:
                self._free_ports(pub)
            self._send(conn, {"cmd": "error", "message": "端口已耗尽"})
            return None
        sid = f"{addr[0]}:{pub}"
        data_q: queue.Queue = queue.Queue()
        self._sessions[sid] = {"ctl": conn, "public_port": pub, "reverse_port": rev,
                               "queue": data_q, "target": None}
        self._send(conn, {"cmd": "assigned", "public_host": self.public_host,
                          "public_port": pub, "reverse_port": rev})
        log.info("隧道注册 %s -> 公网 %s:%s (回连 %s)", addr[0],
                 self.public_host, pub, rev)
        utils.run_thread(self._listen_public, "relay-public", args=(pub, data_q, sid))
        utils.run_thread(self._listen_reverse, "relay-reverse", args=(rev, data_q, sid))
        return sid

    def _cleanup(self, sid: str) -> None:
        s = self._sessions.pop(sid, None)
        if s:
            self._free_ports(s["public_port"], s["reverse_port"])

    # ---- 公网端口：玩家连接，排队并通知客户端 ----
    def _listen_public(self, port: int, data_q: queue.Queue, sid: str) -> None:
        ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind(("0.0.0.0", port))
        ls.listen(64)
        try:
            while True:
                player, _ = ls.accept()
                data_q.put(player)
                s = self._sessions.get(sid)
                if s and s["ctl"]:
                    self._send(s["ctl"], {"cmd": "pipe"})
        except OSError:
            pass
        finally:
            ls.close()

    # ---- 回连端口：客户端数据会话，与排队玩家对接 ----
    def _listen_reverse(self, port: int, data_q: queue.Queue, sid: str) -> None:
        ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind(("0.0.0.0", port))
        ls.listen(64)
        try:
            while True:
                client_conn, _ = ls.accept()
                utils.run_thread(self._serve_reverse, "relay-pipe",
                                 args=(client_conn, data_q, sid))
        except OSError:
            pass
        finally:
            ls.close()

    def _serve_reverse(self, client_conn, data_q, sid) -> None:
        player = None
        deadline = time_mark()
        while player is None:
            try:
                player = data_q.get(timeout=5)
            except queue.Empty:
                if _expired(deadline, 30):
                    break
        if player is None:
            try:
                client_conn.close()
            except Exception:
                pass
            return
        _pump(client_conn, player)

    @staticmethod
    def _send(sock: socket.socket, msg: dict) -> None:
        try:
            sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        except OSError:
            pass


def _pump(a: socket.socket, b: socket.socket) -> None:
    import time
    stop = threading.Event()

    def forward(src, dst):
        try:
            while not stop.is_set():
                d = src.recv(RECV)
                if not d:
                    break
                dst.sendall(d)
        except Exception:
            pass
        finally:
            stop.set()
            for s in (a, b):
                try:
                    s.close()
                except Exception:
                    pass

    t1 = threading.Thread(target=forward, args=(a, b), daemon=True)
    t2 = threading.Thread(target=forward, args=(b, a), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


def time_mark() -> float:
    import time
    return time.time()


def _expired(mark: float, secs: float) -> bool:
    import time
    return time.time() - mark > secs


def main() -> None:
    ap = argparse.ArgumentParser(description="NCL 中继服务器（内网穿透服务端）")
    ap.add_argument("--control-port", type=int, default=6000)
    ap.add_argument("--data-range", default="20000-20100")
    ap.add_argument("--token", default="ncl")
    ap.add_argument("--public-host", default="")
    args = ap.parse_args()
    low, high = args.data_range.split("-")
    RelayServer(args.token, args.control_port, int(low), int(high),
                args.public_host).run()


if __name__ == "__main__":
    main()
