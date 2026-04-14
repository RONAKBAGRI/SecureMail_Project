"""
Node 3 – Delete Server (Gaurav)
==================================
Listens on DELETE_PORT (4503) for deletion requests sent by Node 4
whenever a user deletes an email via the GUI.

Protocol (same length-prefixed framing used by file_pusher / file_receiver):
  → Client sends: 4-byte big-endian payload length
  → Client sends: JSON payload
        {
            "username": "user@project.local",
            "folder":   "inbox" | "spam",
            "filename": "1711902000123.enc"
        }
  ← Server replies: b"ACK" on success, b"ERR" on failure

Started as a daemon thread by smtp_server.py's main().
"""

import socket
import threading
import json
import os
import logging
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

log = logging.getLogger(__name__)


# ── Per-connection handler ────────────────────────────────────────────────────

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes, blocking until complete."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed before all bytes received")
        buf += chunk
    return buf


def _handle_delete(conn: socket.socket, addr):
    try:
        # Read 4-byte big-endian length prefix
        raw_len = _recv_exact(conn, 4)
        length  = int.from_bytes(raw_len, "big")

        if length > 1024:   # deletion payloads are tiny; reject anything large
            log.error(f"[DELETE_SERVER] Oversized payload ({length} B) from {addr[0]}; rejecting.")
            conn.sendall(b"ERR")
            return

        raw  = _recv_exact(conn, length)
        data = json.loads(raw.decode("utf-8"))

        username = data["username"]
        folder   = data["folder"]
        filename = data["filename"]

        # Validate inputs
        if not all(isinstance(v, str) for v in (username, folder, filename)):
            raise ValueError("Non-string field in delete request")
        if folder not in ("inbox", "spam"):
            raise ValueError(f"Invalid folder: {folder!r}")
        if not filename.endswith(".enc"):
            raise ValueError(f"Invalid filename: {filename!r}")

        # Build paths
        base_path = os.path.join(
            config.SHARED_STORAGE_DIR, username, folder, filename
        )
        meta_path = base_path.replace(".enc", ".meta")

        removed = []
        for path in (base_path, meta_path):
            if os.path.exists(path):
                try:
                    os.remove(path)
                    removed.append(os.path.basename(path))
                except OSError as e:
                    log.error(f"[DELETE_SERVER] Could not remove {path}: {e}")

        if removed:
            log.info(f"[DELETE_SERVER] Deleted from Node 3: {removed}")
        else:
            log.warning(
                f"[DELETE_SERVER] Nothing to delete for "
                f"{username}/{folder}/{filename} (may have already been cleaned up)"
            )

        conn.sendall(b"ACK")

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.error(f"[DELETE_SERVER] Bad request from {addr[0]}: {e}")
        try:
            conn.sendall(b"ERR")
        except Exception:
            pass
    except Exception as e:
        log.error(f"[DELETE_SERVER] Unexpected error from {addr[0]}: {e}", exc_info=True)
        try:
            conn.sendall(b"ERR")
        except Exception:
            pass
    finally:
        conn.close()


# ── Server bootstrap ──────────────────────────────────────────────────────────

def start_delete_server():
    """
    Bind on DELETE_PORT and spawn a daemon thread per incoming request.
    Called from smtp_server.py's main() so it starts alongside the SMTP server.
    """
    def _serve():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", config.DELETE_PORT))
        srv.listen(20)
        log.info(f"[DELETE_SERVER] Listening on port {config.DELETE_PORT}")
        while True:
            conn, addr = srv.accept()
            conn.settimeout(10)
            threading.Thread(
                target=_handle_delete,
                args=(conn, addr),
                daemon=True
            ).start()

    threading.Thread(target=_serve, daemon=True, name="DeleteServer").start()
    log.info("[DELETE_SERVER] Delete server thread started.")
