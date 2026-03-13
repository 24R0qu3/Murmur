import json
import socket
import sys

SOCKET_PATH = "/tmp/murmur.sock"
PIPE_NAME = r"\\.\pipe\murmur"
_ERROR_MSG = "Murmur daemon is not running. Start it with: murmur"


class IPCClient:
    def send(self, cmd: dict) -> dict:
        if sys.platform == "win32":
            return self._send_windows(cmd)
        return self._send_unix(cmd)

    def _send_unix(self, cmd: dict) -> dict:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(SOCKET_PATH)
                sock.sendall((json.dumps(cmd) + "\n").encode())
                data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
                return json.loads(data.split(b"\n")[0])
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            raise ConnectionError(_ERROR_MSG)

    def _send_windows(self, cmd: dict) -> dict:
        try:
            import win32file

            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
            try:
                message = (json.dumps(cmd) + "\n").encode()
                win32file.WriteFile(handle, message)
                _, data = win32file.ReadFile(handle, 65536)
                return json.loads(data.split(b"\n")[0])
            finally:
                win32file.CloseHandle(handle)
        except Exception:
            raise ConnectionError(_ERROR_MSG)
