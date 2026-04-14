"""
Node 4 – Registration Server (Sunny)
Listens on REGISTRATION_PORT for new-user requests routed through Node 2.

Protocol (TCP, single exchange):
  Client → "REGISTER <email> <password>\r\n"
  Server → "+OK Registration successful.\r\n"
         | "-ERR <reason>\r\n"
"""
import socket
import threading
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from user_manager import add_user

log = logging.getLogger(__name__)


def _recv_line(sock: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\r\n"):
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("Client disconnected")
        buf += ch
    return buf.decode("utf-8", errors="replace").rstrip("\r\n")


def _handle(conn: socket.socket, addr):
    try:
        line  = _recv_line(conn)
        parts = line.split(None, 2)   # ["REGISTER", email, password]

        if len(parts) != 3 or parts[0].upper() != "REGISTER":
            conn.sendall(b"-ERR Syntax: REGISTER <email> <password>\r\n")
            return

        _, email, password = parts
        success, message   = add_user(email, password)

        if success:
            conn.sendall(f"+OK {message}\r\n".encode())
            log.info(f"[REG] Registered {email} from {addr[0]}")
        else:
            conn.sendall(f"-ERR {message}\r\n".encode())
            log.warning(f"[REG] Rejected {email}: {message}")

    except ConnectionError as e:
        log.warning(f"[REG] {addr[0]} disconnected: {e}")
    except Exception as e:
        log.error(f"[REG] Error: {e}", exc_info=True)
    finally:
        conn.close()


def start_registration_server():
    """Start registration listener as a daemon thread."""
    def _serve():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", config.REGISTRATION_PORT))
        srv.listen(10)
        log.info(f"[REG] Registration server listening on port {config.REGISTRATION_PORT}")
        while True:
            conn, addr = srv.accept()
            conn.settimeout(10)
            threading.Thread(target=_handle, args=(conn, addr), daemon=True).start()

    threading.Thread(target=_serve, daemon=True, name="RegistrationServer").start()
    log.info("[REG] Registration server thread started.")
