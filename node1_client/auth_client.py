"""
Node 1 – Auth Client (Prashant)
Sends REGISTER requests through the proxy to Node 4's registration server.
"""
import socket
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

log = logging.getLogger(__name__)


def _recv_line(sock: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\r\n"):
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("Disconnected")
        buf += ch
    return buf.decode("utf-8", errors="replace").strip()


def register_user(email: str, password: str) -> tuple:
    """
    Register a new user through the proxy.
    Returns (success: bool, message: str).
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((config.PROXY_IP, config.PROXY_PORT))

        sock.sendall(b"ROUTE:REGISTER\r\n")
        ready = _recv_line(sock)
        if ready != "READY":
            return False, f"Proxy not ready: {ready}"

        sock.sendall(f"REGISTER {email} {password}\r\n".encode())
        resp = _recv_line(sock)

        if resp.startswith("+OK"):
            return True, resp[4:].strip() or "Registration successful."
        else:
            reason = resp[5:].strip() if resp.startswith("-ERR") else resp
            return False, reason

    except ConnectionRefusedError:
        return False, "Could not connect to proxy. Is Node 2 running?"
    except socket.timeout:
        return False, "Connection timed out."
    except Exception as e:
        return False, str(e)
    finally:
        if sock:
            sock.close()