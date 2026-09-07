# ipc_helper.py
# -*- coding: utf-8 -*-
"""NekoLink 单实例 IPC：Toast 点击时唤醒已运行的 GUI。"""
from __future__ import annotations

import json
import socket
import threading
from typing import Callable, Optional

HOST = "127.0.0.1"
PORT = 39217


def send_ipc_command(cmd: dict, timeout: float = 2.0) -> bool:
    data = (json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout) as sock:
            sock.sendall(data)
        return True
    except OSError:
        return False


def parse_nekolink_uri(uri: str) -> Optional[dict]:
    uri = (uri or "").strip()
    if not uri.lower().startswith("nekolink://"):
        return None
    rest = uri[len("nekolink://") :]
    if rest.lower().startswith("history/"):
        notif_id = rest.split("/", 1)[1].strip()
        if notif_id:
            return {"cmd": "open_history", "notif_id": notif_id}
    return None


class IpcServer:
    def __init__(self, on_command: Callable[[dict], None]):
        self._on_command = on_command
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="NekoLinkIPC", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def _run(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((HOST, PORT))
            srv.listen(5)
            srv.settimeout(0.5)
            self._sock = srv
            while not self._stop.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with conn:
                    try:
                        raw = conn.recv(4096)
                        if not raw:
                            continue
                        cmd = json.loads(raw.decode("utf-8").strip())
                        if isinstance(cmd, dict):
                            self._on_command(cmd)
                    except Exception:
                        pass
        finally:
            try:
                srv.close()
            except OSError:
                pass
