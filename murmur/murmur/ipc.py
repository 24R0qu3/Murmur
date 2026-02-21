import json
import os
import socket
import sys
import threading
from typing import Callable

SOCKET_PATH = "/tmp/murmur.sock"
PIPE_NAME = r"\\.\pipe\murmur"


class IPCServer:
    def __init__(self):
        self._handler: Callable[[dict], dict] | None = None

    def start(self, handler: Callable[[dict], dict]):
        self._handler = handler
        if sys.platform == "win32":
            t = threading.Thread(target=self._run_windows, daemon=True)
        else:
            t = threading.Thread(target=self._run_unix, daemon=True)
        t.start()

    def _dispatch(self, raw: str) -> str:
        try:
            cmd = json.loads(raw)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"JSON parse error: {e}"}) + "\n"
        try:
            response = self._handler(cmd)
        except Exception as e:
            response = {"error": str(e)}
        return json.dumps(response) + "\n"

    # ── Unix / Linux ──────────────────────────────────────────────────────────

    def _run_unix(self):
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(SOCKET_PATH)
            server.listen(5)
            while True:
                conn, _ = server.accept()
                threading.Thread(
                    target=self._handle_unix_conn, args=(conn,), daemon=True
                ).start()

    def _handle_unix_conn(self, conn: socket.socket):
        with conn:
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    response = self._dispatch(line.decode())
                    conn.sendall(response.encode())

    # ── Windows Named Pipe ────────────────────────────────────────────────────

    def _run_windows(self):
        import pywintypes
        import win32pipe

        while True:
            pipe = win32pipe.CreateNamedPipe(
                PIPE_NAME,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                win32pipe.PIPE_UNLIMITED_INSTANCES,
                65536,
                65536,
                0,
                None,
            )
            try:
                win32pipe.ConnectNamedPipe(pipe, None)
                threading.Thread(
                    target=self._handle_windows_conn, args=(pipe,), daemon=True
                ).start()
            except pywintypes.error:
                import win32file
                win32file.CloseHandle(pipe)

    def _handle_windows_conn(self, pipe):
        import pywintypes
        import win32file

        try:
            buf = b""
            while True:
                try:
                    _, chunk = win32file.ReadFile(pipe, 4096)
                except pywintypes.error:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    response = self._dispatch(line.decode())
                    win32file.WriteFile(pipe, response.encode())
        finally:
            win32file.CloseHandle(pipe)
