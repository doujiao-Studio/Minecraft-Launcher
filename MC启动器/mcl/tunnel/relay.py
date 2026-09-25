"""中继隧道客户端：连接到你自建的公共中继服务器，把本地 MC 端口映射到公网。

原理：客户端与中继服务器保持一条常驻控制连接；中继在公网开放一个数据端口。
当有人连接公网端口时，中继通知客户端，客户端再主动向中继建立一条数据连接
（出站连接，天然穿过 NAT），中继把两条连接对接。全程不需要路由器端口映射，
也不需要公网 IP。
"""
from __future__ import annotations
import json
import socket
import threading
from typing import Callable, Optional

from .. import utils

log = utils.get_logger("tunnel")

RECV_SIZE = 65536


class TunnelError(Exception):
    pass


class TunnelClient:
    def __init__(self, relay_host: str, control_port: int,
                 token: str, target_host: str = "127.0.0.1",
                 target_port: int = 25565,
                 on_status: Optional[Callable[[str], None]] = None,
                 on_data: Optional[Callable[[str], None]] = None):
        self.relay_host = relay_host
        self.control_port = int(control_port)
        self.token = token
        self.target_host = target_host
        self.target_port = int(target_port)
        self.on_status = on_status or (lambda s: None)
        self.on_data = on_data or (lambda s: None)
        self.public_host = ""
        self.public_port = 0
        self.reverse_port = 0
        self.control: Optional[socket.socket] = None
        self._stop = threading.Event()
        self._running = False

    # ---- 生命周期 ----

    def start(self) -> None:
        if self._running:
            return
        self._stop.clear()
        self._running = True
        utils.run_thread(self._control_loop, "tunnel-control")

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self.control:
            try:
                self.control.close()
            except Exception:
                pass
        self.on_status("隧道已停止")

    def _notify(self, s: str) -> None:
        self.on_status(s)
        log.info(s)

    def _control_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._connect_and_serve()
            except Exception as e:
                if self._stop.is_set():
                    break
                self._notify(f"中继连接断开，5 秒后重连: {e}")
                self._stop.wait(5)

    def _connect_and_serve(self) -> None:
        ctl = socket.create_connection((self.relay_host, self.control_port),
                                       timeout=10)
        ctl.settimeout(45)  # 控制通道读写超时，配合心跳保活
        self.control = ctl
        reg = {"cmd": "register", "token": self.token,
               "target_host": self.target_host, "target_port": self.target_port}
        ctl.sendall((json.dumps(reg) + "\n").encode("utf-8"))
        self._notify(f"已连接中继 {self.relay_host}:{self.control_port}，等待分配端口…")
        buf = ""
        last_send = 0.0
        while not self._stop.is_set():
            try:
                data = ctl.recv(RECV_SIZE)
            except socket.timeout:
                # 心跳
                if last_send and (utils.now() - last_send) > 25:
                    ctl.sendall((json.dumps({"cmd": "ping"}) + "\n").encode("utf-8"))
                    last_send = utils.now()
                continue
            except OSError:
                break
            if not data:
                break
            buf += data.decode("utf-8", errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                self._handle_message(ctl, json.loads(line))

    def _handle_message(self, ctl: socket.socket, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "assigned":
            self.public_host = msg.get("public_host", self.relay_host)
            self.public_port = int(msg.get("public_port", 0))
            self.reverse_port = int(msg.get("reverse_port", self.public_port))
            self._notify(f"隧道建立成功！好友用地址 {self.public_host}:{self.public_port} 连接")
        elif cmd == "pipe":
            # 有玩家连上了公网端口，我们主动建立数据会话
            utils.run_thread(self._open_data_session, "tunnel-data")
        elif cmd == "pong":
            pass
        elif cmd == "error":
            self._notify(f"中继错误: {msg.get('message', '未知')}")

    def _open_data_session(self) -> None:
        try:
            ds = socket.create_connection((self.relay_host, self.reverse_port),
                                          timeout=10)
            ds.settimeout(None)
            # 连接本地目标
            ts = socket.create_connection((self.target_host, self.target_port),
                                          timeout=5)
            ts.settimeout(None)
            self._pump(ds, ts)
        except Exception as e:
            self.on_data(f"[隧道] 数据会话失败: {e}")

    def _pump(self, a: socket.socket, b: socket.socket) -> None:
        """双向转发，直到任一端关闭。"""
        stop = threading.Event()

        def forward(src, dst):
            try:
                while not stop.is_set():
                    d = src.recv(RECV_SIZE)
                    if not d:
                        break
                    dst.sendall(d)
            except Exception:
                pass
            finally:
                stop.set()
                try:
                    a.close()
                    b.close()
                except Exception:
                    pass

        t1 = threading.Thread(target=forward, args=(a, b), daemon=True)
        t2 = threading.Thread(target=forward, args=(b, a), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
